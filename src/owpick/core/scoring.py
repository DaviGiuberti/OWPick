"""scoring.py — Modelo de scoring e ranking (OWPick v1.2.2). Puro, zero I/O.

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
    raw_e          = λ · Σ_a C(e,a) + μ · m(e,k) + ν · Σ_{e'≠e} Y(e,e')
                                                               (sinal bruto de ameaça; 0 = neutro:
                                                                counters + força no mapa + sinergia
                                                                do inimigo com o time inimigo)
    w_e            = exp(A · tanh(raw_e / S))                  (multiplicador de ameaça — ver
                     threat_multiplier: w_e(0)=1, log-simétrico, ancorado em
                     w(−6)=0.5 e w(8)=2.5)
    T_syn(h)       = Σ_a  Y(h, a) · β_syn(h, a)                (sinergia, diagonal ignorada;
                                                                β_syn(h,a) = β_syn_sup_sup se
                                                                ambos forem SUP e o preset o
                                                                definir — só o "counter-first" —,
                                                                senão β_syn)

As estatísticas (DataFrame de winrate/pickrate) e as matrizes já normalizadas
chegam POR PARÂMETRO — a leitura de xlsx/csv é responsabilidade da infra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

import numpy as np
import pandas as pd

from owpick.core import heroes
from owpick.core.heroes import normalize_hero_name
from owpick.core.models import BanList, Hero, Lineup, Recommendation
from owpick.log import get_logger

log = get_logger("scoring")


# ---------------------------------------------------------------------------
# Parâmetros do modelo
# ---------------------------------------------------------------------------
EPS = 0.001  # piso numérico da pickrate (NÃO é proxy de amostra)
MMAX = 3.0  # limite (clamp) do z-score em desvios-padrão
ALPHA = 2.25  # escala FINAL do MetaStrength (multiplica conf·z já clampado)
LAMBDA = 0.25  # intensidade do threat weighting (componente counter)
MU_THREAT = 0.3  # intensidade do threat weighting (componente MetaStrength do inimigo no mapa)
NU_THREAT = 0.10  # intensidade do threat weighting (componente sinergia DENTRO do time inimigo)
BETA_META = 1.5  # peso do MetaStrength no score (preset "equilibrado"; era 2.0)
BETA_CTR = 1.0  # peso do counter term no score
BETA_SYN = 0.65  # peso da sinergia (mantido do modelo anterior)


# ---------------------------------------------------------------------------
# Enemy threat — transforma o sinal bruto (raw) em multiplicador de ameaça
# ---------------------------------------------------------------------------
# w(raw) = exp(A · tanh(raw / S))   (A = ln do teto assintótico; S = escala)
#   • raw = λ·Σ C(e,a) + μ·m(e,k)      →  raw = 0  ⇔  ameaça neutra
#   • w(0) = 1 exatamente; raw < 0 ⇒ w < 1; raw > 0 ⇒ w > 1
#   • contínua, suave (C∞), estritamente monotônica (preserva a ordenação) e
#     log-simétrica: w(−raw) = 1/w(raw); tanh ∈ (−1, 1) ⇒ w ∈ (e^−A, e^A),
#     então NUNCA explode nem fica não-positivo
#   • A curva é ANCORADA em dois pontos escolhidos (fonte única): passa
#     EXATAMENTE por (raw, w) = (−1.5, 0.6) e (3.0, 2.5). As âncoras ficam
#     DENTRO da faixa real de raw (~[−2, +2] com as matrizes reais: Σ C(e,a) tem
#     std≈2.31 e m(e,k) std≈0.88; raw = λ·ΣC + μ·m), então o multiplicador
#     responde de fato ao preset: na faixa típica w varia em ~[0.6, 1.7] em vez
#     de ficar quase preso em 1.0. (As âncoras antigas −6/+8 ficavam a ~10σ da
#     faixa real e deixavam a curva praticamente reta — w∈~[0.97, 1.05].)
THREAT_ANCHOR_LOW = (-1.5, 0.6)  # (raw, w) do lado negativo
THREAT_ANCHOR_HIGH = (3.0, 2.5)  # (raw, w) do lado positivo


def _fit_log_symmetric(
    anchor_lo: tuple[float, float], anchor_hi: tuple[float, float]
) -> tuple[float, float]:
    """Ajusta (A, S) de w(raw) = exp(A·tanh(raw/S)) para passar por dois pontos.

    Não há forma fechada: `S` sai por bisseção (a razão
    tanh(r_hi/S)/tanh(r_lo/S) é monotônica em S) e `A` do anchor positivo.
    `w(0) = 1` é automático (tanh(0) = 0). Roda uma vez, no import.
    """
    (r_lo, w_lo), (r_hi, w_hi) = anchor_lo, anchor_hi
    y_lo, y_hi = math.log(w_lo), math.log(w_hi)  # y_lo < 0 < y_hi
    target = y_hi / y_lo  # = tanh(r_hi/S) / tanh(r_lo/S) (< 0)
    lo, hi = 1e-6, 1e6  # bisseção geométrica (S varia em ordens de grandeza)
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        # a razão decresce em S; se está acima do alvo, S é pequeno demais
        if math.tanh(r_hi / mid) / math.tanh(r_lo / mid) > target:
            lo = mid
        else:
            hi = mid
    scale = math.sqrt(lo * hi)
    log_cap = y_hi / math.tanh(r_hi / scale)
    return log_cap, scale


THREAT_LOG_CAP, THREAT_SCALE = _fit_log_symmetric(THREAT_ANCHOR_LOW, THREAT_ANCHOR_HIGH)


def threat_multiplier(
    raw: float, log_cap: float = THREAT_LOG_CAP, scale: float = THREAT_SCALE
) -> float:
    """Multiplicador de ameaça a partir do sinal bruto `raw` (0 = neutro).

    w(raw) = exp(log_cap · tanh(raw / scale)). Contínua, suave (C∞) e
    estritamente monotônica em `raw` (preserva a ordenação das ameaças), com
    w(0) = 1 e w ∈ (e^−log_cap, e^+log_cap) por construção — o multiplicador
    jamais explode nem fica não-positivo (o antigo piso `W_MIN` some por design).
    Ancorada em w(−1.5) = 0.6 e w(3.0) = 2.5 (ver THREAT_ANCHOR_*).
    """
    return math.exp(log_cap * math.tanh(raw / scale))


NEUTRAL_WEIGHT = threat_multiplier(0.0)  # 1.0 — ameaça neutra (raw = 0)


# ---------------------------------------------------------------------------
# Pesos do modelo ajustáveis via presets (tarefa 6.3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelWeights:
    """Conjunto de α/λ/μ/β do modelo. Defaults = comportamento atual."""

    alpha: float = ALPHA  # escala do MetaStrength
    lam: float = LAMBDA  # threat weighting (componente counter)
    mu: float = MU_THREAT  # threat weighting (componente mapa)
    nu: float = NU_THREAT  # threat weighting (componente sinergia do time inimigo)
    beta_meta: float = BETA_META  # peso do MetaStrength no score
    beta_ctr: float = BETA_CTR  # peso do counter term no score
    beta_syn: float = BETA_SYN  # peso da sinergia no score
    # Peso de sinergia específico para pares SUP × SUP; None ⇒ usa `beta_syn`.
    beta_syn_sup_sup: float | None = None


DEFAULT_WEIGHTS = ModelWeights()

# Presets nomeados (settings.json: weights_preset). "equilibrado" = o modelo
# atual; os demais reponderam os termos mantendo a mesma estrutura da fórmula.
PRESETS: dict[str, ModelWeights] = {
    # O modelo padrão (β_meta=1.5). Base dos demais presets.
    "equilibrado": DEFAULT_WEIGHTS,
    # Prioriza counterar o time inimigo: threat weighting por COUNTERS (λ=0.32) e
    # counter term cheio (β_ctr=1.0); meta recua (β_meta=0.75) e a sinergia geral
    # também (β_syn=0.325), EXCETO entre dois suportes (β_syn_sup_sup=0.65), onde a
    # dupla de sup pesa como no preset equilibrado.
    "counter-first": ModelWeights(
        lam=0.32,
        mu=0.23,
        nu=0.10,
        beta_meta=0.75,
        beta_ctr=1.00,
        beta_syn=0.325,
        beta_syn_sup_sup=0.65,
    ),
    # Prioriza o desempenho estatístico no mapa atual (meta): β_meta=3.0. A ameaça
    # passa a pesar quem é FORTE NO MAPA (μ=0.70) e quem forma uma COMP COESA
    # (ν=0.15) mais que os counters brutos (λ=0.20).
    "meta-first": ModelWeights(lam=0.20, mu=0.70, nu=0.15, beta_meta=3.0, beta_ctr=1.0, beta_syn=0.65),
    # "Conforto+": mais sinergia no SEU time (β_syn=1.25) e ameaça inimiga
    # DE-ENFATIZADA em todos os eixos (λ=0.18, μ=0.20, ν=0.06) — o foco é o SEU time.
    "conforto+": ModelWeights(lam=0.18, mu=0.20, nu=0.06, beta_syn=1.25),
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
    synergy_matrix: dict[str, dict[str, float]] | None = None,
    nu: float = NU_THREAT,
) -> dict[str, float]:
    """
    Para cada inimigo e:
        raw = λ · Σ_a C(e,a) + μ · m(e,k) + ν · Σ_{e'≠e} Y(e,e')
        w_e = threat_multiplier(raw) = exp(A · tanh(raw / S))

    Três componentes do sinal bruto de ameaça (0 = neutro):
      • λ · Σ_a C(e,a)      — quão bem o inimigo countera o SEU time (counters).
      • μ · m(e,k)          — força do inimigo no mapa atual (MetaStrength).
      • ν · Σ_{e'≠e} Y(e,e') — sinergia do inimigo com o RESTO do time inimigo
                               (combo: um inimigo numa comp coesa é mais perigoso;
                               anti-sinergia com os companheiros reduz a ameaça).
                               `Y` é a MESMA matriz de sinergia dos aliados
                               (`synergy_matrix`), aplicada aos pares de inimigos;
                               `None` ⇒ termo ausente (compatibilidade).

    `raw = 0` dá w_e = 1 exatamente; raw < 0 ⇒ w_e < 1; raw > 0 ⇒ w_e > 1.
    `threat_multiplier` é contínuo, suave, monotônico (preserva a ordenação das
    ameaças) e log-simétrico. Retorna {nome_normalizado_do_inimigo: w_e}.
    """
    allies_norm = [normalize_hero_name(a) for a in allies if a]
    enemies_norm = [normalize_hero_name(e) for e in enemies if e]
    meta = meta_strength or {}
    syn = synergy_matrix or {}
    weights: dict[str, float] = {}
    for enemy in enemies:
        if not enemy:
            continue
        en = normalize_hero_name(enemy)
        row = enemy_matrix.get(en, {})
        counter_sum = sum(row.get(a, 0.0) for a in allies_norm)
        map_bonus = meta.get(en, 0.0)  # MetaStrength do inimigo no mapa atual
        syn_row = syn.get(en, {})
        # Sinergia com os OUTROS inimigos (diagonal e' == e ignorada).
        synergy_sum = sum(syn_row.get(other, 0.0) for other in enemies_norm if other != en)
        raw = lam * counter_sum + mu * map_bonus + nu * synergy_sum
        weights[en] = threat_multiplier(raw)
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
    # razão legível, na MESMA escala das colunas da tabela. As três colunas
    # (META, COUNTER, SYNERGY) são as contribuições JÁ PONDERADAS que entram no
    # TOTAL — cada peso (β_meta/β_ctr/β_syn) é aplicado AQUI, uma única vez —, de
    # forma que vale exatamente TOTAL = META + COUNTER + SYNERGY (o usuário
    # confere a soma olhando a tabela). Os números das razões batem com as colunas.
    REASON_MIN = 0.05  # contribuições abaixo disso são ruído e não explicam nada
    counter_reasons: list[tuple[float, str]] = []
    synergy_reasons: list[tuple[float, str]] = []

    # --- counter term (threat weighting × β_ctr) ---
    enemy_row = enemy_matrix.get(hn, {})
    counter_score = 0.0
    for enemy in enemies:
        if not enemy:
            continue
        en = normalize_hero_name(enemy)
        if en in enemy_row:
            w_e = threat_weights.get(en, 1.0)
            contribution = weights.beta_ctr * w_e * enemy_row[en]
            counter_score += contribution
            if contribution >= REASON_MIN:
                counter_reasons.append(
                    (contribution, f"countera {enemy} (+{contribution:.2f}, ameaça {w_e:.2f})")
                )
            elif contribution <= -REASON_MIN:
                counter_reasons.append((contribution, f"sofre contra {enemy} ({contribution:.2f})"))

    # --- synergy term (× β_syn, diagonal ignorada) ---
    # β_syn_sup_sup (se definido no preset) substitui β_syn quando AMBOS os heróis
    # do par são suportes; qualquer outra combinação de roles usa β_syn.
    ally_row = ally_matrix.get(hn, {})
    hero_is_sup = weights.beta_syn_sup_sup is not None and heroes.get_hero_role(hn) == "SUP"
    synergy_score = 0.0
    for ally in allies:
        if not ally:
            continue
        an = normalize_hero_name(ally)
        if an == hn:
            continue  # diagonal: remove o antigo hack do -11
        if an in ally_row:
            beta = weights.beta_syn
            if hero_is_sup and heroes.get_hero_role(an) == "SUP":
                assert weights.beta_syn_sup_sup is not None
                beta = weights.beta_syn_sup_sup
            contribution = ally_row[an] * beta
            synergy_score += contribution
            if contribution >= REASON_MIN:
                synergy_reasons.append((contribution, f"sinergia com {ally} (+{contribution:.2f})"))
            elif contribution <= -REASON_MIN:
                synergy_reasons.append(
                    (contribution, f"anti-sinergia com {ally} ({contribution:.2f})")
                )

    # --- meta term (× β_meta) ---
    meta_score = weights.beta_meta * meta_strength.get(hn, 0.0)

    total = meta_score + counter_score + synergy_score

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
