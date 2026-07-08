"""Testes da explicabilidade do ranking (tarefa 6.4)."""

import pytest

from owpick import settings
from owpick.core.scoring import calculate_hero_score, rank_heroes


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    yield tmp_path
    settings.reload()


ENEMY_MATRIX = {"zarya": {"wrecking-ball": 1.0, "dva": 0.7, "tracer": -0.6}}
ALLY_MATRIX = {"zarya": {"mei": 1.2, "ana": 0.01}}
THREAT = {"wrecking-ball": 1.9, "dva": 1.4, "tracer": 1.0}
META = {"zarya": 1.2}


def _score():
    return calculate_hero_score(
        "Zarya",
        ALLY_MATRIX,
        ENEMY_MATRIX,
        allies=["Mei", "Ana"],
        enemies=["Wrecking Ball", "D.Va", "Tracer"],
        threat_weights=THREAT,
        meta_strength=META,
        mapa="Ilios",
    )


def test_reasons_decompoem_counter_sinergia_e_mapa():
    reasons = _score()["reasons"]
    assert isinstance(reasons, list)
    text = " | ".join(reasons)
    # Counter ponderado por ameaça: 1.9 * 1.0 = 1.90 (inimigo que mais pesou).
    assert "countera Wrecking Ball (+1.90, ameaça 1.90)" in text
    assert "countera D.Va" in text
    # Contribuição negativa vira "sofre contra".
    assert "sofre contra Tracer" in text
    # Sinergia relevante aparece; a desprezível (0.01·β) fica de fora.
    assert "sinergia com Mei" in text
    assert "Ana" not in text
    # Influência do mapa por último (já ponderada por β_meta: 2.0 · 1.20 = 2.40).
    assert reasons[-1] == "forte em Ilios (+2.40)"


def test_reasons_ordenadas_por_impacto():
    reasons = _score()["reasons"]
    assert isinstance(reasons, list)
    # Counters vêm primeiro, do maior para o menor impacto.
    assert reasons[0].startswith("countera Wrecking Ball")
    assert reasons[1].startswith("countera D.Va")


def test_rank_heroes_preenche_reasons():
    recs, _ = rank_heroes(
        ["Zarya"],
        allies=["Mei"],
        enemies=["Wrecking Ball"],
        ally_matrix=ALLY_MATRIX,
        enemy_matrix=ENEMY_MATRIX,
        threat_weights=THREAT,
        meta_strength=META,
        mapa="Ilios",
    )
    assert recs[0].reasons  # campo Recommendation.reasons alimentado
    assert any("Wrecking Ball" in r for r in recs[0].reasons)


def test_mapa_unknown_nao_gera_razao_de_mapa():
    data = calculate_hero_score(
        "Zarya",
        ALLY_MATRIX,
        ENEMY_MATRIX,
        allies=[],
        enemies=[],
        threat_weights={},
        meta_strength=META,
        mapa="UNKNOWN",
    )
    reasons = data["reasons"]
    assert isinstance(reasons, list)
    assert not any("forte em" in r or "fraco em" in r for r in reasons)


# ---------------------------------------------------------------------------
# Exibição condicionada ao settings (liga/desliga persistido)
# ---------------------------------------------------------------------------
def _fake_result():
    from owpick.core.models import Hero, Recommendation
    from owpick.pipeline import RankingResult

    rec = Recommendation(
        hero=Hero.from_name("Zarya"),
        meta=1.2,
        counter=1.9,
        synergy=0.8,
        total=3.9,
        reasons=["countera Wrecking Ball (+1.90, ameaça 1.90)"],
    )
    return RankingResult(
        role="TANK",
        playable=["Zarya"],
        allies=["Mei"],
        enemies=["Wrecking Ball"],
        banned=[],
        mapa="Ilios",
        meta_available=True,
        threat_weights={"wrecking-ball": 1.9},
        recommendations=[rec],
    )


def test_render_mostra_explicacao_somente_quando_ativada(isolated_settings, capsys):
    from owpick.ui import ranking_view

    ranking_view.render(_fake_result())
    assert "Por quê" not in capsys.readouterr().out  # default: desativada

    settings.save(settings.Settings(explain_ranking=True))
    ranking_view.render(_fake_result())
    out = capsys.readouterr().out
    assert "Por quê" in out
    assert "countera Wrecking Ball" in out
