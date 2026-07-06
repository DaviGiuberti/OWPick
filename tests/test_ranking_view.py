"""Smoke test da apresentação rich do ranking (tarefa 6.5)."""

import pytest

from owpick import settings
from owpick.core.models import Hero, Recommendation
from owpick.pipeline import RankingResult
from owpick.ui import ranking_view


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    yield tmp_path
    settings.reload()


def _result() -> RankingResult:
    recs = [
        Recommendation(hero=Hero.from_name(n), meta=m, counter=c, synergy=s, total=m + c + s)
        for n, m, c, s in [
            ("Zarya", 1.0, 2.0, 0.5),
            ("Ana", 0.5, 1.0, 0.2),
            ("Ashe", 0.0, -0.5, 0.1),
        ]
    ]
    return RankingResult(
        role="ALL",
        playable=["Zarya", "Ana", "Ashe"],
        allies=["Mei"],
        enemies=["Winston", "Tracer"],
        banned=["Sombra"],
        mapa="Ilios",
        meta_available=True,
        threat_weights={"winston": 1.8, "tracer": 1.2},
        recommendations=recs,
    )


def test_render_rich_contem_tabela_ameacas_e_dados(isolated_settings, capsys):
    ranking_view.render(_result())
    out = capsys.readouterr().out
    # Cabeçalho e painel de ameaças.
    assert "Mapa atual: Ilios" in out
    assert "Ranking de Ameaças Inimigas" in out
    assert "Winston" in out and "1.80" in out
    # Tabela com colunas e heróis.
    for token in ("RANK", "HERO", "MAP META", "COUNTER", "SYNERGY", "TOTAL"):
        assert token in out
    for hero in ("Zarya", "Ana", "Ashe"):
        assert hero in out
    # Barra de score presente para o melhor colocado.
    assert "█" in out
    assert "Banidos: Sombra" in out
