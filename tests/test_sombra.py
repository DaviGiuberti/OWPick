"""Matrizes da Sombra Suporte — pesquisa pós-rework (Season 5, v1.2.18).

A v1.2.16 limpou a linha/coluna da Sombra (os números eram da Sombra DPS, outro
kit). A pesquisa pós-rework da v1.2.18 preencheu:

- **counters** contra os outros 53 heróis: counter rating do counterwatch.gg na
  Season 5 (150.601 partidas), convertido com os limiares calibrados na D.Mon
  (|r| < 3.0 -> 0, < 11.5 -> ±1, >= 11.5 -> ±2) e espelhado (antissimétrico);
- **sinergias** só contra DPS e Tanks: dado de dupla do counterwatch (2 pontos),
  guias e vídeos (1 ponto cada); sem evidência, a média de Kiriko, Brigitte e
  Jetpack Cat (suportes de perfil mais próximo), arredondada para o neutro.

O bloco SUP x SUP continua o da categoria Meio (tests/test_suportes.py). A
metodologia está em DOCUMENTACAO.md ("Tabela do Doctrine e da Sombra").
"""

from __future__ import annotations

import pytest

from owpick.core import heroes, scoring
from owpick.core.heroes import normalize_hero_name
from owpick.infra import datasource
from owpick.infra.resources import resource_path

HERO = "Sombra"
KEY = "sombra"


def _matrices():
    return datasource.get_ally_matrix(), datasource.get_enemy_matrix()


def _k(name: str) -> str:
    return normalize_hero_name(name)


def _keys(*roles: str) -> set[str]:
    return {_k(h) for r in roles for h in heroes.HEROES_ROLES[r]}


def _meta():
    return scoring.load_meta_strength(
        datasource.read_stats_inputs(resource_path(datasource.STATS_FILE)), "Ilios"
    )


def _reasons(score: dict) -> list[str]:
    reasons = score["reasons"]
    assert isinstance(reasons, list)
    return reasons


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
def test_counters_completos_antissimetricos_e_na_escala():
    _ally, enemy = _matrices()
    outros = {_k(h) for h in heroes.get_all_heroes()} - {KEY}
    assert set(enemy[KEY]) == outros  # a diagonal fica vazia
    assert {h for h, row in enemy.items() if KEY in row} == outros
    for x in outros:
        assert enemy[KEY][x] == -enemy[x][KEY], x
        assert -2 <= enemy[x][KEY] <= 2, x


@pytest.mark.parametrize(
    "heroi,valor",
    [
        # Quem mais pune a Sombra (rating +7.9 / +6.6 / +6.3).
        ("Baptiste", 1),
        ("Venture", 1),
        ("Tracer", 1),
        ("Doomfist", 1),
        # Abaixo do limiar (+2.9); uma fonte só (SenseOS) não move o valor.
        ("Sojourn", 0),
        # Abaixo do limiar; fontes em conflito no Winston (games.gg x Samito).
        ("Winston", 0),
        ("Genji", 0),
        # Quem ela pune: tanks grandes (Mauga -11.7 é o único ±2).
        ("Mauga", -2),
        ("Junker Queen", -1),
        ("Roadhog", -1),
        ("Bastion", -1),
        ("Doctrine", -1),
        # Revisão da D.Mon (rating ±0.9 nas duas páginas): era +1 desde a v1.2.16.
        ("D.Mon", 0),
    ],
)
def test_counters_ancorados_na_pesquisa(heroi, valor):
    """C(X, Sombra) = quanto X countera a Sombra (positivo = X leva vantagem)."""
    _ally, enemy = _matrices()
    assert enemy[_k(heroi)][KEY] == valor


# ---------------------------------------------------------------------------
# Sinergias: só DPS e Tanks mudaram
# ---------------------------------------------------------------------------
def test_sinergias_completas_contra_dps_e_tanks_na_escala():
    ally, _enemy = _matrices()
    for x in _keys("DPS", "TANK"):
        assert x in ally[KEY] and KEY in ally[x], x
        assert -2 <= ally[KEY][x] <= 2 and -2 <= ally[x][KEY] <= 2, x


@pytest.mark.parametrize(
    "heroi,valor",
    [
        # Dado de dupla + guia + vídeo (>= 3 pontos).
        ("Tracer", 2),
        ("Genji", 2),
        ("Winston", 2),
        ("Doomfist", 2),
        # Dado de dupla (2 pontos).
        ("Hazard", 1),
        ("Vendetta", 1),
        ("Anran", 1),
        ("Pharah", 1),
        ("Soldier: 76", 1),
        # Um guia ou vídeo (1 ponto).
        ("Wrecking Ball", 1),
        ("Venture", 1),
        ("Zarya", 1),
        ("Hanzo", 1),
        # Mantido da v1.2.16.
        ("D.Mon", 1),
    ],
)
def test_sinergias_com_evidencia_valem_nos_dois_sentidos(heroi, valor):
    ally, _enemy = _matrices()
    assert ally[KEY][_k(heroi)] == valor
    assert ally[_k(heroi)][KEY] == valor


@pytest.mark.parametrize(
    "heroi,linha,coluna",
    [
        # Sem evidência: linha = média das linhas de Kiriko/Brigitte/Jetpack Cat,
        # coluna = média das colunas — as assimetrias da planilha se repetem.
        ("Cassidy", 0, 2),
        ("Widowmaker", 0, -1),
        ("Domina", -1, 0),
        ("Ramattra", 1, 1),
        ("Reinhardt", 0, 0),
    ],
)
def test_sinergias_sem_evidencia_seguem_os_suportes_de_perfil_proximo(heroi, linha, coluna):
    ally, _enemy = _matrices()
    fb = [_k(s) for s in ("Kiriko", "Brigitte", "Jetpack Cat")]
    x = _k(heroi)
    assert ally[KEY][x] == linha
    assert ally[x][KEY] == coluna
    # A regra que gerou o valor: |média| <= 0.5 -> 0, senão arredonda.
    media_linha = sum(ally[s][x] for s in fb) / 3
    assert linha == (0 if abs(media_linha) <= 0.5 else round(media_linha))


def test_mercy_x_sombra_continua_a_da_categoria():
    """A pesquisa só mexeu em DPS e Tanks: Mercy x Sombra segue Main x Meio."""
    ally, _enemy = _matrices()
    assert ally["mercy"][KEY] == ally[KEY]["mercy"] == -8
    assert ally[KEY][KEY] == -11


# ---------------------------------------------------------------------------
# Scoring — Sombra inimiga, aliada e candidata
# ---------------------------------------------------------------------------
def test_sombra_inimiga_vira_ameaca_contra_tanks_grandes():
    ally, enemy = _matrices()
    meta = _meta()
    allies = ["Mauga", "Junker Queen"]  # C(Sombra, ·) = +2 e +1
    w = scoring.compute_threat_weights([HERO], enemy, allies, meta, synergy_matrix=ally)
    assert w[KEY] > scoring.NEUTRAL_WEIGHT

    data = scoring.calculate_hero_score("Tracer", ally, enemy, allies, [HERO], w, meta)
    assert data["counter_score"] == pytest.approx(1 * w[KEY])  # C(Tracer, Sombra) = +1
    assert any(r.startswith(f"countera {HERO}") for r in _reasons(data))


def test_sombra_aliada_soma_sinergia_para_dps():
    ally, enemy = _matrices()
    meta = _meta()
    beta = scoring.DEFAULT_WEIGHTS.beta_syn
    for candidato, y in (("Genji", 2), ("Cassidy", 2), ("Widowmaker", -1), ("Reinhardt", 0)):
        com = scoring.calculate_hero_score(candidato, ally, enemy, [HERO, "Ana"], [], {}, meta)
        sem = scoring.calculate_hero_score(candidato, ally, enemy, ["Ana"], [], {}, meta)
        delta = float(com["synergy_score"]) - float(sem["synergy_score"])  # pyright: ignore[reportArgumentType]
        assert delta == pytest.approx(y * beta), candidato


def test_sombra_candidata_pontua_counter_e_sinergia():
    ally, enemy = _matrices()
    meta = _meta()
    enemies = ["Mauga"]
    w = scoring.compute_threat_weights(enemies, enemy, ["Winston"], meta, synergy_matrix=ally)
    data = scoring.calculate_hero_score(HERO, ally, enemy, ["Winston"], enemies, w, meta)
    assert data["counter_score"] == pytest.approx(2 * w["mauga"])
    assert data["synergy_score"] == pytest.approx(2 * scoring.DEFAULT_WEIGHTS.beta_syn)
    soma = sum(float(data[k]) for k in ("meta_score", "counter_score", "synergy_score"))  # pyright: ignore[reportArgumentType]
    assert data["total"] == pytest.approx(soma)
