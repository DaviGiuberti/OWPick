"""
enemy_mult.py — Peso de ameaça (threat weight) de um herói inimigo.

Utilitário de diagnóstico (fora do pipeline principal): apenas mais um
consumidor da camada core (owpick.core.scoring) + infra (owpick.infra). O
threat weighting de produção é calculado em owpick.core.scoring; este script
serve para inspecionar um inimigo isolado.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ferramenta externa: os módulos do app vivem em src/owpick.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from owpick.core.heroes import normalize_hero_name  # noqa: E402
from owpick.core.scoring import _softplus  # noqa: E402
from owpick.infra import datasource, storage  # noqa: E402

LAMBDA = 0.25  # intensidade do threat weighting (espelha owpick.core.scoring)


def calculate_threat_weight(
    hero: str,
    enemy_matrix: dict[str, dict[str, float]],
    opponents_of_enemy: list[str],
    lam: float = LAMBDA,
) -> float:
    """
    w_e = softplus(1 + λ · Σ_a C(hero, a)), a ∈ opponents_of_enemy (aliados do
    jogador). C(hero, a) = quanto o herói inimigo countera o aliado a.
    """
    hn = normalize_hero_name(hero)
    row = enemy_matrix.get(hn, {})
    threat_sum = sum(row.get(normalize_hero_name(a), 0.0) for a in opponents_of_enemy)
    return _softplus(1.0 + lam * threat_sum)


def executar(hero: str, enemy_matrix: dict[str, dict[str, float]] | None = None) -> float:
    """Peso de ameaça do herói inimigo informado (lê lineup.txt do disco)."""
    try:
        # Sob a perspectiva do inimigo, os 'opponents' são os aliados do jogador.
        opponents_of_enemy, _teammates = storage.read_lineup()
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem primeiro.")
        return 1.0

    if enemy_matrix is None:
        try:
            enemy_matrix = datasource.get_enemy_matrix()
        except FileNotFoundError as e:
            print(f"ERRO CRÍTICO: Não foi possível ler a planilha de counters: {e}")
            return 1.0

    weight = calculate_threat_weight(hero, enemy_matrix, opponents_of_enemy)
    print(f"Heroi inimigo avaliado : {hero} -> Threat weight: {weight:.2f}")
    return weight
