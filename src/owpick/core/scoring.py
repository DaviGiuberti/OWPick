"""scoring.py — Modelo de scoring e ranking (OWPick v1.2.0). Puro, zero I/O.

Score final de cada herói candidato h:

    S(h) = β_meta · m_scaled(h, k) + β_ctr · T_ctr(h) + T_syn(h)

onde:
    m_scaled(h, k) = MetaStrength do herói no mapa atual k. É o z-score da
                     winrate BRUTA do herói DENTRO DA SUA ROLE, atenuado pela
                     confiança vinda da pickrate (sem shrinkage), escalado por α:
                         m(h,k) = α · clip(conf · z_role, −Mmax, +Mmax)
                         z_role = (wr(h) − wr̄_role) / σ_role
                         conf   = pr / (pr + k0_role),  k0_role = pickrate neutra da role
    T_ctr(h)       = Σ_e  w_e · C(h, e)                        (counter com threat weighting)
    w_e            = softplus(1 + λ · Σ_a C(e,a) + μ · m(e,k)) (peso de ameaça do inimigo e,
                     inclui desempenho do inimigo no mapa atual; softplus > 0 sempre)
    T_syn(h)       = Σ_a  Y(h, a) · β_syn                      (sinergia, diagonal ignorada)

As estatísticas (DataFrame de winrate/pickrate) e as matrizes já normalizadas
chegam POR PARÂMETRO — a leitura de xlsx/csv é responsabilidade da infra.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

import numpy as np
import pandas as pd

from owpick.core import heroes
from owpick.core.heroes import normalize_hero_name
from owpick.core.models import BanList, Hero, Lineup, Recommendation
from owpick.log import get_logger

log = get_logger("scoring")


def _softplus(x: float) -> float:
    """Softplus numericamente estável: ln(1 + e^x) == logaddexp(0, x).

    Usa np.logaddexp para evitar overflow de e^x quando x é grande. O resultado
    é sempre > 0 e monotônico em x, então preserva a ordenação das ameaças sem
    precisar de um piso (W_MIN deixou de ser o mecanismo de não-negatividade).
    """
    return float(np.logaddexp(0.0, x))


# ---------------------------------------------------------------------------
# Parâmetros do modelo (ver §3.5 da especificação)
# ---------------------------------------------------------------------------
EPS = 0.001  # piso numérico da pickrate (NÃO é proxy de amostra)
MMAX = 3.0  # limite (clamp) do z-score em desvios-padrão
ALPHA = 2.25  # escala FINAL do MetaStrength (multiplica conf·z já clampado)
LAMBDA = 0.25  # intensidade do threat weighting (componente counter)
MU_THREAT = 0.3  # intensidade do threat weighting (componente MetaStrength do inimigo no mapa)
BETA_META = 1.0  # peso do MetaStrength no score
BETA_CTR = 1.0  # peso do counter term no score
BETA_SYN = 0.65  # peso da sinergia (mantido do modelo anterior)
NEUTRAL_WEIGHT = _softplus(1.0)  # ≈ 1.313 — peso de ameaça neutro (raw = 1)


# ---------------------------------------------------------------------------
# Pesos do modelo ajustáveis via presets (tarefa 6.3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelWeights:
    """Conjunto de α/λ/μ/β do modelo. Defaults = comportamento atual."""

    alpha: float = ALPHA  # escala do MetaStrength
    lam: float = LAMBDA  # threat weighting (componente counter)
    mu: float = MU_THREAT  # threat weighting (componente mapa)
    beta_meta: float = BETA_META  # peso do MetaStrength no score
    beta_ctr: float = BETA_CTR  # peso do counter term no score
    beta_syn: float = BETA_SYN  # peso da sinergia no score


DEFAULT_WEIGHTS = ModelWeights()

# Presets nomeados (settings.json: weights_preset). "equilibrado" = o modelo
# atual; os demais reponderam os termos mantendo a mesma estrutura da fórmula.
PRESETS: dict[str, ModelWeights] = {
    # O modelo padrão, sem alterações.
    "equilibrado": DEFAULT_WEIGHTS,
    # Prioriza counterar o time inimigo: counter term e threat weighting mais
    # fortes; meta e sinergia recuam.
    "counter-first": ModelWeights(lam=0.40, beta_meta=0.75, beta_ctr=1.50, beta_syn=0.50),
    # Prioriza o desempenho estatístico no mapa atual (meta).
    "meta-first": ModelWeights(beta_meta=1.50, beta_ctr=0.75, beta_syn=0.50),
    # "Conforto+": valoriza jogar o que combina com o SEU time (sinergia),
    # aceitando recomendações menos agressivas contra o time inimigo.
    "conforto+": ModelWeights(beta_meta=0.85, beta_ctr=0.85, beta_syn=1.00),
}

WEIGHT_FIELD_NAMES = tuple(f.name for f in fields(ModelWeights))

# Rótulo curto de cada preset (o que ele prioriza), exibido no menu de escolha.
# Fica junto de PRESETS para não sair de sincronia; a chave é o mesmo nome
# gravado em settings.weights_preset.
PRESET_LABELS: dict[str, str] = {
    "equilibrado": "Equilibrado (padrão) — balanceia meta, counter e sinergia",
    "counter-first": "Counter-first — prioriza counterar o time inimigo",
    "meta-first": "Meta-first — prioriza o desempenho estatístico no mapa atual",
    "conforto+": "Conforto+ — valoriza a sinergia com o seu próprio time",
}


def resolve_weights(
    preset: str = "equilibrado", custom: dict[str, float] | None = None
) -> ModelWeights:
    """
    Pesos efetivos: parte do preset nomeado (desconhecido → "equilibrado") e
    aplica os overrides do modo avançado (`custom` = {campo: valor}, campos
    desconhecidos ignorados — a validação com aviso vive no settings).
    """
    base = PRESETS.get(preset, DEFAULT_WEIGHTS)
    if custom:
        overrides = {k: float(v) for k, v in custom.items() if k in WEIGHT_FIELD_NAMES}
        if overrides:
            base = replace(base, **overrides)
    return base


# ---------------------------------------------------------------------------
# MetaStrength m(h, k) — força do herói no mapa atual
# ---------------------------------------------------------------------------
def load_meta_strength(
    df: pd.DataFrame,
    mapa_atual: str,
    eps: float = EPS,
    mmax: float = MMAX,
    alpha: float = ALPHA,
) -> dict[str, float]:
    """
    A partir do DataFrame de stats (winrate/pickrate por mapa), retorna
    {nome_normalizado: MetaStrength} para o mapa atual. Heróis sem dados (ou
    mapa desconhecido) resultam em ausência da chave -> tratado como 0.0.

    m(h,k) = alpha · clip(conf · z_role, −mmax, +mmax)
    z_role = (wr(h) − wr̄_role) / σ_role      (por role, sobre winrate bruta)
    conf   = pr / (pr + k0_role),  k0_role = pickrate neutra da role
    """
    result: dict[str, float] = {}
    if not mapa_atual or mapa_atual == "UNKNOWN":
        return result

    df_map = df[df["map"] == mapa_atual].copy()
    if df_map.empty:
        # Fallback: comparação tolerante a acentuação/capitalização.
        target = normalize_hero_name(mapa_atual)
        mask = df["map"].apply(lambda m: normalize_hero_name(str(m)) == target)
        df_map = df[mask].copy()
    if df_map.empty:
        log.debug("mapa '%s' sem dados em stats_inputs.csv", mapa_atual)
        return result

    df_map["winrate"] = pd.to_numeric(df_map["winrate"], errors="coerce")
    df_map["pickrate"] = pd.to_numeric(df_map["pickrate"], errors="coerce")
    valid = df_map.dropna(subset=["winrate"])  # pyright: ignore[reportCallIssue] — stubs do pandas
    if valid.empty:
        return result

    pr_neutral = heroes.get_role_neutral_pickrates()

    # Estatísticas POR ROLE, sobre a winrate BRUTA (não encolhida): cada herói é
    # comparado apenas com heróis da mesma função.
    role_stats: dict[str, tuple[float, float]] = {
        str(role): (float(grp["winrate"].mean()), float(grp["winrate"].std()))  # pyright: ignore[reportArgumentType]
        for role, grp in valid.groupby("role")
    }

    for _, row in valid.iterrows():
        hero = row["hero"]
        role = row.get("role")
        wr = float(row["winrate"])  # pyright: ignore[reportArgumentType]
        pr_pct = row["pickrate"]
        pr = (float(pr_pct) / 100.0) if pd.notna(pr_pct) else eps  # pyright: ignore[reportArgumentType, reportGeneralTypeIssues]
        pr = max(pr, eps)  # eps aqui é apenas piso numérico (NÃO é proxy de amostra)

        wr_bar_role, sigma_role = role_stats.get(str(role), (wr, 0.0))
        if sigma_role == 0.0 or np.isnan(sigma_role):
            result[normalize_hero_name(str(hero))] = 0.0
            continue

        k0 = pr_neutral.get(str(role), 0.10)
        conf = pr / (pr + k0)
        z = (wr - wr_bar_role) / sigma_role
        result[normalize_hero_name(str(hero))] = alpha * float(np.clip(conf * z, -mmax, mmax))
    return result


# ---------------------------------------------------------------------------
# Threat weighting — peso de ameaça de cada inimigo
# ---------------------------------------------------------------------------
def compute_threat_weights(
    enemies: list[str],
    enemy_matrix: dict[str, dict[str, float]],
    allies: list[str],
    meta_strength: dict[str, float] | None = None,
    lam: float = LAMBDA,
    mu: float = MU_THREAT,
) -> dict[str, float]:
    """
    Para cada inimigo e:
        raw = 1 + λ · Σ_a C(e,a) + μ · m(e,k)
        w_e = softplus(raw) = ln(1 + e^raw)

    O softplus é sempre > 0 e monotônico em `raw`, então preserva a ordenação
    das ameaças (mais counter/mais meta -> maior w_e) sem colapsar ameaças
    baixas num piso. Retorna {nome_normalizado_do_inimigo: w_e}.
    """
    allies_norm = [normalize_hero_name(a) for a in allies if a]
    meta = meta_strength or {}
    weights: dict[str, float] = {}
    for enemy in enemies:
        if not enemy:
            continue
        en = normalize_hero_name(enemy)
        row = enemy_matrix.get(en, {})
        counter_sum = sum(row.get(a, 0.0) for a in allies_norm)
        map_bonus = meta.get(en, 0.0)  # MetaStrength do inimigo no mapa atual
        raw = 1.0 + lam * counter_sum + mu * map_bonus
        weights[en] = _softplus(raw)
    return weights


# ---------------------------------------------------------------------------
# Score de um herói candidato
# ---------------------------------------------------------------------------
def calculate_hero_score(
    hero_name: str,
    ally_matrix: dict[str, dict[str, float]],
    enemy_matrix: dict[str, dict[str, float]],
    allies: list[str],
    enemies: list[str],
    threat_weights: dict[str, float],
    meta_strength: dict[str, float],
    weights: ModelWeights = DEFAULT_WEIGHTS,
    mapa: str | None = None,
) -> dict[str, float | str | list[str]]:
    hn = normalize_hero_name(hero_name)

    # Contribuições por origem (tarefa 6.4): cada termo relevante gera uma
    # razão legível, na MESMA escala das colunas da tabela (CTR = w_e·C sem
    # β_ctr; SYN = Y·β_syn; META = m_scaled) — os números batem com o ranking.
    REASON_MIN = 0.05  # contribuições abaixo disso são ruído e não explicam nada
    counter_reasons: list[tuple[float, str]] = []
    synergy_reasons: list[tuple[float, str]] = []

    # --- counter term (com threat weighting) ---
    enemy_row = enemy_matrix.get(hn, {})
    counter_score = 0.0
    for enemy in enemies:
        if not enemy:
            continue
        en = normalize_hero_name(enemy)
        if en in enemy_row:
            w_e = threat_weights.get(en, 1.0)
            contribution = w_e * enemy_row[en]
            counter_score += contribution
            if contribution >= REASON_MIN:
                counter_reasons.append(
                    (contribution, f"countera {enemy} (+{contribution:.2f}, ameaça {w_e:.2f})")
                )
            elif contribution <= -REASON_MIN:
                counter_reasons.append((contribution, f"sofre contra {enemy} ({contribution:.2f})"))

    # --- synergy term (diagonal ignorada) ---
    ally_row = ally_matrix.get(hn, {})
    synergy_score = 0.0
    for ally in allies:
        if not ally:
            continue
        an = normalize_hero_name(ally)
        if an == hn:
            continue  # diagonal: remove o antigo hack do -11
        if an in ally_row:
            contribution = ally_row[an] * weights.beta_syn
            synergy_score += contribution
            if contribution >= REASON_MIN:
                synergy_reasons.append((contribution, f"sinergia com {ally} (+{contribution:.2f})"))
            elif contribution <= -REASON_MIN:
                synergy_reasons.append(
                    (contribution, f"anti-sinergia com {ally} ({contribution:.2f})")
                )

    # --- meta term ---
    meta_score = meta_strength.get(hn, 0.0)

    total = weights.beta_meta * meta_score + weights.beta_ctr * counter_score + synergy_score

    # Razões ordenadas pelo IMPACTO (|contribuição|, desc) dentro de cada termo;
    # counters primeiro, depois sinergias, mapa por último.
    reasons = [
        r
        for _, r in sorted(counter_reasons, key=lambda c: abs(c[0]), reverse=True)
        + sorted(synergy_reasons, key=lambda c: abs(c[0]), reverse=True)
    ]
    if mapa and mapa != "UNKNOWN":
        if meta_score >= REASON_MIN:
            reasons.append(f"forte em {mapa} (+{meta_score:.2f})")
        elif meta_score <= -REASON_MIN:
            reasons.append(f"fraco em {mapa} ({meta_score:.2f})")

    return {
        "hero": hero_name,
        "meta_score": meta_score,
        "counter_score": counter_score,
        "synergy_score": synergy_score,
        "total": total,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Ranking completo (caso de uso puro) -> list[Recommendation]
# ---------------------------------------------------------------------------
def rank_heroes(
    playable_heroes: list[str],
    allies: list[str],
    enemies: list[str],
    ally_matrix: dict[str, dict[str, float]],
    enemy_matrix: dict[str, dict[str, float]],
    threat_weights: dict[str, float],
    meta_strength: dict[str, float],
    excluded_keys: set[str] | None = None,
    weights: ModelWeights = DEFAULT_WEIGHTS,
    mapa: str | None = None,
) -> tuple[list[Recommendation], list[str]]:
    """
    Ranqueia os heróis jogáveis, excluindo quem estiver em `excluded_keys`
    (aliados já no time + banidos). Retorna (recomendações ordenadas desc,
    nomes excluídos). Puro — não imprime nem lê nada.
    """
    excluded = excluded_keys or set()
    recs: list[Recommendation] = []
    excluded_names: list[str] = []
    for hero_name in playable_heroes:
        if normalize_hero_name(hero_name) in excluded:
            excluded_names.append(hero_name)
            continue
        data = calculate_hero_score(
            hero_name,
            ally_matrix,
            enemy_matrix,
            allies,
            enemies,
            threat_weights,
            meta_strength,
            weights=weights,
            mapa=mapa,
        )
        reasons = data["reasons"]
        assert isinstance(reasons, list)
        recs.append(
            Recommendation(
                hero=Hero.from_name(hero_name),
                meta=float(data["meta_score"]),  # pyright: ignore[reportArgumentType]
                counter=float(data["counter_score"]),  # pyright: ignore[reportArgumentType]
                synergy=float(data["synergy_score"]),  # pyright: ignore[reportArgumentType]
                total=float(data["total"]),  # pyright: ignore[reportArgumentType]
                reasons=reasons,
            )
        )
    recs.sort(key=lambda r: r.total, reverse=True)
    return recs, excluded_names


def excluded_keys(lineup: Lineup, bans: BanList) -> set[str]:
    """Chaves normalizadas indisponíveis: aliados já no time + banidos."""
    return lineup.ally_keys() | bans.keys()
