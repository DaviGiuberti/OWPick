"""
enemy_mult.py — Peso de ameaça (threat weight) de um herói inimigo.

A partir do OWPick v1.1.0 o threat weighting é calculado diretamente em
choose_ow_hero.py (sobre a matriz já carregada), de modo que este módulo
NÃO é mais necessário no pipeline principal. Ele é mantido como utilitário
para inspeção/diagnóstico de um inimigo isolado.

Mudanças em relação à versão anterior:
  - Usa utils.resource_path / utils.read_heroes_* (sem duplicação).
  - Aceita a matriz de counters pré-carregada (evita reler a planilha do disco).
  - Substitui o multiplicador hardcoded (total/4)+1 pelo threat weighting:
        w_e = softplus(1 + λ · Σ_a C(e, a)) = ln(1 + e^raw)
  - Nomes de variáveis explícitos sobre a perspectiva invertida do lineup.

A partir do OWPick v1.1.2 o peso usa softplus (sempre > 0, monotônico) em vez
do antigo piso max(W_MIN, ...), em sincronia com choose_ow_hero.py.
"""

import numpy as np

from typing import Dict, List, Optional

import utils
from utils import normalize_hero_name

# Estes valores espelham os de choose_ow_hero.py — mantenha-os em sincronia.
LAMBDA = 0.25   # intensidade do threat weighting
W_MIN = 0.1     # (inerte) compat; softplus garante positividade


def _softplus(x: float) -> float:
    """Softplus numericamente estável: ln(1 + e^x) == logaddexp(0, x)."""
    return float(np.logaddexp(0.0, x))


def read_lineup(filepath: str = "lineup.txt"):
    """
    Lê o lineup.txt SOB A PERSPECTIVA DO HERÓI INIMIGO avaliado (invertida em
    relação a choose_ow_hero.py — isto é intencional):

      - linhas [:4]  → opponents_of_enemy : quem o inimigo enfrenta
                       (= os ALIADOS do jogador)
      - linhas [4:9] → teammates_of_enemy : o time do inimigo
                       (= os INIMIGOS do jogador, incluindo ele próprio)

    O peso de ameaça mede o quanto o inimigo countera o time do jogador, por
    isso o relevante são os 'opponents_of_enemy' (linhas [:4]).
    """
    import os
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    opponents_of_enemy = [a for a in lines[:4] if a]   # aliados do jogador
    teammates_of_enemy = [e for e in lines[4:9] if e]  # inimigos do jogador
    return opponents_of_enemy, teammates_of_enemy


def calculate_threat_weight(hero: str,
                            enemy_matrix: Dict[str, Dict[str, float]],
                            opponents_of_enemy: List[str],
                            lam: float = LAMBDA,
                            w_min: float = W_MIN) -> float:
    """
    w_e = softplus(1 + λ · Σ_a C(hero, a)), a ∈ opponents_of_enemy.
    C(hero, a) = quanto o herói inimigo countera o aliado a do jogador.

    O `w_min` é inerte (mantido por compat de assinatura): softplus já é > 0.
    """
    del w_min  # inerte: softplus garante positividade
    hn = normalize_hero_name(hero)
    row = enemy_matrix.get(hn, {})
    threat_sum = sum(row.get(normalize_hero_name(a), 0.0) for a in opponents_of_enemy)
    return _softplus(1.0 + lam * threat_sum)


def executar(hero: str,
             enemy_matrix: Optional[Dict[str, Dict[str, float]]] = None) -> float:
    """
    Retorna o peso de ameaça (threat weight) do herói inimigo informado.

    Parâmetros
    ----------
    hero : str
        Nome do herói inimigo a avaliar.
    enemy_matrix : dict, opcional
        Matriz de counters já carregada (utils.build_matrix_dict). Se omitida,
        a planilha é lida do disco uma única vez aqui.
    """
    try:
        opponents_of_enemy, _teammates_of_enemy = read_lineup()
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem primeiro.")
        return 1.0

    if enemy_matrix is None:
        try:
            enemy_matrix = utils.get_enemy_matrix()  # cacheado
        except FileNotFoundError as e:
            print(f"ERRO CRÍTICO: Não foi possível ler a planilha de counters: {e}")
            return 1.0

    weight = calculate_threat_weight(hero, enemy_matrix, opponents_of_enemy)
    print(f"Heroi inimigo avaliado : {hero} -> Threat weight: {weight:.2f}")
    return weight
