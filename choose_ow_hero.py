"""
choose_ow_hero.py — Scoring e ranking de heróis (modelo OWPick v2).

Score final de cada herói candidato h:

    S(h) = β_meta · m_scaled(h, k) + β_ctr · T_ctr(h) + T_syn(h)

onde:
    m_scaled(h, k) = MetaStrength do herói no mapa atual k (z-score do winrate
                     ajustado por shrinkage, escalado por α)
    T_ctr(h)       = Σ_e  w_e · C(h, e)              (counter com threat weighting)
    w_e            = max(0.1, 1 + λ · Σ_a C(e, a))   (peso de ameaça do inimigo e)
    T_syn(h)       = Σ_a  Y(h, a) · β_syn            (sinergia, diagonal ignorada)

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


# ---------------------------------------------------------------------------
# Parâmetros do modelo (ver §3.5 da especificação)
# ---------------------------------------------------------------------------
KAPPA_BASE = 100.0   # pseudo-contagem base do shrinkage
EPS = 0.001          # mínimo para evitar divisão por zero na pickrate
MMAX = 3.0           # limite (clamp) do z-score em desvios-padrão
ALPHA = 1.0          # escala do MetaStrength
LAMBDA = 0.25        # intensidade do threat weighting
BETA_META = 1.0      # peso do MetaStrength no score
BETA_CTR = 1.0       # peso do counter term no score
BETA_SYN = 0.65      # peso da sinergia (mantido do modelo anterior)
W_MIN = 0.1          # piso do peso de ameaça (w_e não fica negativo)


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
                       kappa_base: float = KAPPA_BASE,
                       eps: float = EPS,
                       mmax: float = MMAX,
                       alpha: float = ALPHA) -> Dict[str, float]:
    """
    Lê stats_inputs.csv e retorna {nome_normalizado: MetaStrength} para o mapa
    atual. Heróis sem dados (ou mapa desconhecido) resultam em ausência da
    chave -> MetaStrength tratado como 0.0 no scoring.

    Adaptação importante: o stats_inputs.csv gerado por coletar_stats.py NÃO
    possui a coluna 'games' prevista na especificação, e winrate/pickrate estão
    em percentual. Usa-se a pickrate (em fração) como proxy de amostra ('g') e o
    κ_eff por pickrate relativa conforme §3.2. O z-score final é invariante à
    unidade (percentual vs. fração), pois normaliza pelo desvio-padrão do mapa.
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

    wr_bar = float(valid["winrate"].mean())
    pr_neutral = utils.get_role_neutral_pickrates()

    wr_adj: Dict[str, float] = {}
    for _, row in valid.iterrows():
        hero = row["hero"]
        role = row.get("role")
        wr = float(row["winrate"])
        pr_pct = row["pickrate"]
        pr = (float(pr_pct) / 100.0) if pd.notna(pr_pct) else eps
        pr = max(pr, eps)

        prn = pr_neutral.get(role)
        kappa = kappa_base * (prn / pr) if prn is not None else kappa_base

        g = pr  # pickrate (fração) como proxy de amostra (sem coluna 'games')
        wr_adj[normalize_hero_name(hero)] = (g * wr + kappa * wr_bar) / (g + kappa)

    values = np.array(list(wr_adj.values()), dtype=float)
    sigma = float(values.std())
    if sigma == 0.0 or np.isnan(sigma):
        return {hero: 0.0 for hero in wr_adj}

    for hero, adj in wr_adj.items():
        z = (adj - wr_bar) / sigma
        result[hero] = alpha * float(np.clip(z, -mmax, mmax))
    return result


# ---------------------------------------------------------------------------
# Threat weighting — peso de ameaça de cada inimigo
# ---------------------------------------------------------------------------
def compute_threat_weights(enemies: List[str],
                           enemy_matrix: Dict[str, Dict[str, float]],
                           allies: List[str],
                           lam: float = LAMBDA,
                           w_min: float = W_MIN) -> Dict[str, float]:
    """
    Para cada inimigo e: w_e = max(w_min, 1 + λ · Σ_a C(e, a)).
    C(e, a) = quanto o inimigo e countera o aliado a.
    Retorna {nome_normalizado_do_inimigo: w_e}.
    """
    allies_norm = [normalize_hero_name(a) for a in allies if a]
    weights: Dict[str, float] = {}
    for enemy in enemies:
        if not enemy:
            continue
        en = normalize_hero_name(enemy)
        row = enemy_matrix.get(en, {})
        threat_sum = sum(row.get(a, 0.0) for a in allies_norm)
        weights[en] = max(w_min, 1.0 + lam * threat_sum)
    return weights


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

    print("=" * 74)
    print(f"{'RANK':<5} | {'HERO':<18} | {'META':>7} | {'CTR':>8} | {'SYN':>7} | {'TOTAL':>8}")
    print("=" * 74)
    for rank, data in enumerate(sorted_rankings, start=1):
        print(
            f"{rank:<5} | "
            f"{data['hero']:<18} | "
            f"{data['meta_score']:>7.2f} | "
            f"{data['counter_score']:>8.2f} | "
            f"{data['synergy_score']:>7.2f} | "
            f"{data['total']:>8.2f}"
        )
    print("-" * 74)


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

    # Threat weighting por inimigo (substitui o multiplicador (total/4)+1).
    threat_weights = compute_threat_weights(enemies, enemy_matrix, allies)

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
