"""
choose_ow_hero.py — Scoring e ranking de heróis (modelo OWPick v1.1.2).

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

Heróis já presentes no time aliado são EXCLUÍDOS do ranking (regra rígida,
substitui o antigo hack do -11 na diagonal de sinergia).

As planilhas são lidas uma única vez e convertidas em dicionários com chaves
normalizadas (utils.normalize_hero_name), o que torna o scoring tolerante às
diferenças de nomenclatura entre planilhas/templates ("DVa", "Soldier 76") e
heroes_roles.json/stats_inputs.csv ("D.Va", "Soldier: 76").
"""

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import utils
from utils import resource_path, normalize_hero_name  # noqa: F401 (compat)


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
EPS = 0.001          # piso numérico da pickrate (NÃO é proxy de amostra)
MMAX = 3.0           # limite (clamp) do z-score em desvios-padrão
ALPHA = 2.25         # escala FINAL do MetaStrength (multiplica conf·z já clampado)
LAMBDA = 0.25        # intensidade do threat weighting (componente counter)
MU_THREAT = 0.3      # intensidade do threat weighting (componente MetaStrength do inimigo no mapa)
BETA_META = 1.0      # peso do MetaStrength no score
BETA_CTR = 1.0       # peso do counter term no score
BETA_SYN = 0.65      # peso da sinergia (mantido do modelo anterior)
W_MIN = 0.35         # (inerte) compat de assinatura; softplus garante w_e > 0
NEUTRAL_WEIGHT = _softplus(1.0)  # ≈ 1.313 — peso de ameaça neutro (raw = 1)


# ---------------------------------------------------------------------------
# Leitura de arquivos de entrada (gerados em runtime, no diretório de trabalho)
# ---------------------------------------------------------------------------
def read_role() -> Optional[str]:
    role_file = "Roles.txt"
    if not os.path.exists(role_file):
        print("Arquivo 'Roles.txt' não encontrado!")
        print("Por favor, defina sua Role (DPS, Support, Tank ou AllRoles)")
        return None

    with open(role_file, "r", encoding="utf-8") as f:
        role = f.read().strip()

    if not role:
        print("Arquivo 'Roles.txt' está vazio!")
        print("Por favor, defina sua Role (DPS, Support, Tank ou AllRoles)")
        return None

    role_heroes_file = f"{role}.txt"
    if not os.path.exists(role_heroes_file):
        print(f"Arquivo '{role_heroes_file}' não encontrado!")
        print("Por favor, defina seus Personagens Favoritos.")
        return None

    return role


def read_playable_heroes(role: str) -> List[str]:
    role_file = f"{role}.txt"
    with open(role_file, "r", encoding="utf-8") as f:
        heroes = [line.strip() for line in f.readlines() if line.strip()]
    return heroes


def read_lineup(filepath: str = "lineup.txt") -> Tuple[List[str], List[str]]:
    """Lê lineup.txt: linhas [:4] = aliados; linhas [4:9] = inimigos."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    allies = [a for a in lines[:4] if a]
    enemies = [e for e in lines[4:9] if e]
    return allies, enemies


def read_current_map(filepath: str = "current_map.txt") -> str:
    """Lê current_map.txt (gerado por map.py). 'UNKNOWN' se ausente/vazio."""
    if not os.path.exists(filepath):
        return "UNKNOWN"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            mapa = f.read().strip()
        return mapa or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# MetaStrength m(h, k) — força do herói no mapa atual
# ---------------------------------------------------------------------------
def load_meta_strength(mapa_atual: str,
                       eps: float = EPS,
                       mmax: float = MMAX,
                       alpha: float = ALPHA) -> Dict[str, float]:
    """
    Lê stats_inputs.csv e retorna {nome_normalizado: MetaStrength} para o mapa
    atual. Heróis sem dados (ou mapa desconhecido) resultam em ausência da
    chave -> MetaStrength tratado como 0.0 no scoring.

    Modelo (OWPick v1.1.2): o MetaStrength é o z-score da winrate BRUTA do herói
    DENTRO DA SUA ROLE (DPS/TANK/SUP), atenuado pela confiança vinda da pickrate:

        m(h,k) = alpha · clip(conf · z_role, −mmax, +mmax)
        z_role = (wr(h) − wr̄_role) / σ_role
        conf   = pr / (pr + k0_role),   k0_role = pickrate neutra da role

    Estatísticas por role evitam comparar um DPS com a média global (puxada por
    tanks/supports). conf ∈ [0, 1] expressa o quanto a pickrate deixa confiar na
    winrate: vale 0.5 quando o herói é jogado na taxa média da sua role.
    """
    result: Dict[str, float] = {}
    if not mapa_atual or mapa_atual == "UNKNOWN":
        return result

    try:
        df = utils.read_stats_inputs()  # cacheado (lido uma única vez)
    except Exception as e:  # noqa: BLE001
        print(f"[meta] AVISO: não foi possível ler stats_inputs.csv: {e}")
        return result

    df_map = df[df["map"] == mapa_atual].copy()
    if df_map.empty:
        # Fallback: comparação tolerante a acentuação/capitalização.
        target = normalize_hero_name(mapa_atual)
        mask = df["map"].apply(lambda m: normalize_hero_name(str(m)) == target)
        df_map = df[mask].copy()
    if df_map.empty:
        print(f"[meta] Mapa '{mapa_atual}' sem dados em stats_inputs.csv.")
        return result

    df_map["winrate"] = pd.to_numeric(df_map["winrate"], errors="coerce")
    df_map["pickrate"] = pd.to_numeric(df_map["pickrate"], errors="coerce")
    valid = df_map.dropna(subset=["winrate"])
    if valid.empty:
        return result

    pr_neutral = utils.get_role_neutral_pickrates()

    # (1)(2) Estatísticas POR ROLE, calculadas sobre a winrate BRUTA (não encolhida).
    #         Cada herói é comparado apenas com heróis da mesma função.
    role_stats: Dict[str, Tuple[float, float]] = {
        str(role): (float(grp["winrate"].mean()), float(grp["winrate"].std()))
        for role, grp in valid.groupby("role")
    }

    for _, row in valid.iterrows():
        hero = row["hero"]
        role = row.get("role")
        wr = float(row["winrate"])
        pr_pct = row["pickrate"]
        pr = (float(pr_pct) / 100.0) if pd.notna(pr_pct) else eps
        pr = max(pr, eps)  # eps aqui é apenas piso numérico de pickrate (NÃO é proxy de amostra)

        wr_bar_role, sigma_role = role_stats.get(str(role), (wr, 0.0))
        if sigma_role == 0.0 or np.isnan(sigma_role):
            result[normalize_hero_name(hero)] = 0.0
            continue

        # (3) Confiança estatística vinda da pickrate. k0 = pickrate neutra da role,
        #     então conf = 0.5 quando o herói é jogado na taxa média da sua role;
        #     acima dela confia-se mais na winrate, abaixo menos. conf ∈ [0, 1].
        k0 = pr_neutral.get(role, 0.10)
        conf = pr / (pr + k0)

        # (4) z-score da winrate BRUTA, dentro da própria role.
        z = (wr - wr_bar_role) / sigma_role

        result[normalize_hero_name(hero)] = alpha * float(np.clip(conf * z, -mmax, mmax))
    return result


# ---------------------------------------------------------------------------
# Threat weighting — peso de ameaça de cada inimigo
# ---------------------------------------------------------------------------
def compute_threat_weights(enemies: List[str],
                           enemy_matrix: Dict[str, Dict[str, float]],
                           allies: List[str],
                           meta_strength: Optional[Dict[str, float]] = None,
                           lam: float = LAMBDA,
                           mu: float = MU_THREAT,
                           w_min: float = W_MIN) -> Dict[str, float]:
    """
    Para cada inimigo e:
        raw = 1 + λ · Σ_a C(e,a) + μ · m(e,k)
        w_e = softplus(raw) = ln(1 + e^raw)

    C(e,a)  = quanto o inimigo e countera o aliado a.
    m(e,k)  = MetaStrength do inimigo e no mapa atual k (0.0 se desconhecido).
    λ       = intensidade do componente counter.
    μ       = intensidade do componente mapa (força do inimigo no mapa atual).

    O softplus é sempre > 0 e monotônico em `raw`, então preserva a ordenação
    das ameaças (mais counter/mais meta -> maior w_e) sem colapsar ameaças baixas
    no piso. O parâmetro `w_min` permanece por compatibilidade, mas é inerte.

    Retorna {nome_normalizado_do_inimigo: w_e}.
    """
    del w_min  # inerte: softplus garante positividade (mantido só por compat de assinatura)
    allies_norm = [normalize_hero_name(a) for a in allies if a]
    meta = meta_strength or {}
    weights: Dict[str, float] = {}
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


def print_threat_ranking(enemies: List[str],
                         threat_weights: Dict[str, float]) -> None:
    """Exibe no terminal o ranking de ameaça dos heróis inimigos (maior → menor)."""
    if not enemies:
        return
    sorted_enemies = sorted(
        [(e, threat_weights.get(normalize_hero_name(e), NEUTRAL_WEIGHT)) for e in enemies if e],
        key=lambda x: x[1],
        reverse=True,
    )
    print("\n--- Ranking de Ameaças Inimigas ---")
    ordinals = ["1º", "2º", "3º", "4º", "5º"]
    for i, (name, score) in enumerate(sorted_enemies):
        ord_str = ordinals[i] if i < len(ordinals) else f"{i+1}º"
        print(f"  {ord_str} {name:<18} Ameaça: {score:.2f}")
    print("-" * 36)


# ---------------------------------------------------------------------------
# Score de um herói candidato
# ---------------------------------------------------------------------------
def calculate_hero_score(hero_name: str,
                         ally_matrix: Dict[str, Dict[str, float]],
                         enemy_matrix: Dict[str, Dict[str, float]],
                         allies: List[str],
                         enemies: List[str],
                         threat_weights: Dict[str, float],
                         meta_strength: Dict[str, float]) -> Dict[str, float]:
    hn = normalize_hero_name(hero_name)

    # --- counter term (com threat weighting) ---
    enemy_row = enemy_matrix.get(hn, {})
    counter_score = 0.0
    for enemy in enemies:
        if not enemy:
            continue
        en = normalize_hero_name(enemy)
        if en in enemy_row:
            counter_score += threat_weights.get(en, 1.0) * enemy_row[en]

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
            synergy_score += ally_row[an] * BETA_SYN

    # --- meta term ---
    meta_score = meta_strength.get(hn, 0.0)

    total = BETA_META * meta_score + BETA_CTR * counter_score + synergy_score

    return {
        "hero": hero_name,
        "meta_score": meta_score,
        "counter_score": counter_score,
        "synergy_score": synergy_score,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Impressão do ranking
# ---------------------------------------------------------------------------
def print_ranking(rankings: List[Dict[str, float]]) -> None:
    sorted_rankings = sorted(rankings, key=lambda x: x["total"], reverse=True)

    print("=" * 86)
    print(f"{'RANK':<5} | {'HERO':<18} | {'MAP META':>7} | {'COUNTER':>8} | {'SYNERGY':>7} | {'TOTAL':>8}")
    print("=" * 86)
    for rank, data in enumerate(sorted_rankings, start=1):
        print(
            f"{rank:<5} | "
            f"{data['hero']:<18} | "
            f"{data['meta_score']:>7.2f} | "
            f"{data['counter_score']:>8.2f} | "
            f"{data['synergy_score']:>7.2f} | "
            f"{data['total']:>8.2f}"
        )
    print("-" * 86)


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------
def run_hero_ranking():
    role = read_role()
    if role is None:
        return
    print(f"Role selecionada: {role}\n")

    playable_heroes = read_playable_heroes(role)
    print(f"Heróis disponíveis: {', '.join(playable_heroes)}\n")

    try:
        allies, enemies = read_lineup()
        print(f"Aliados: {', '.join(allies)}")
        print(f"Inimigos: {', '.join(enemies)}")
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem (TAB+1) primeiro.")
        return

    mapa_atual = read_current_map()
    print(f"Mapa atual: {mapa_atual}\n")

    try:
        # Matrizes normalizadas, lidas/convertidas uma única vez (cache em utils).
        ally_matrix = utils.get_ally_matrix()
        enemy_matrix = utils.get_enemy_matrix()
    except FileNotFoundError as e:
        print(f"ERRO CRÍTICO: Não foi possível ler as planilhas de dados: {e}")
        return

    # MetaStrength do mapa atual (vazio se UNKNOWN ou sem dados).
    meta_strength = load_meta_strength(mapa_atual)
    if not meta_strength:
        print("MetaStrength indisponível para este mapa — termo tratado como 0.\n")

    # Threat weighting por inimigo — incorpora counters E desempenho no mapa atual.
    threat_weights = compute_threat_weights(enemies, enemy_matrix, allies, meta_strength)

    # Exibe o ranking de ameaças antes da recomendação.
    print_threat_ranking(enemies, threat_weights)

    # Heróis já no time aliado são excluídos do ranking (regra rígida).
    allies_norm = {normalize_hero_name(a) for a in allies if a}

    rankings: List[Dict[str, float]] = []
    excluded: List[str] = []
    for hero in playable_heroes:
        if normalize_hero_name(hero) in allies_norm:
            excluded.append(hero)
            continue
        rankings.append(
            calculate_hero_score(
                hero, ally_matrix, enemy_matrix,
                allies, enemies, threat_weights, meta_strength,
            )
        )

    if excluded:
        print(f"Excluídos (já no time aliado): {', '.join(excluded)}\n")

    if not rankings:
        print("Nenhum herói candidato disponível para ranquear.")
        return

    print_ranking(rankings)


if __name__ == "__main__":
    run_hero_ranking()
