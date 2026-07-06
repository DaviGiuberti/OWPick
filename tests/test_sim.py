"""Testes do modo manual / simulação (tarefa 6.7)."""

import pytest

from owpick import settings
from owpick.infra import storage
from owpick.ui import sim


@pytest.fixture
def user_env(tmp_path, monkeypatch):
    """APPDATA isolado com Role e favoritos prontos para simular."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    from owpick import paths

    paths.ensure_dirs()
    storage.write_role("TANK")
    with open(paths.user_file("TANK.txt"), "w", encoding="utf-8") as f:
        f.write("Zarya\nWinston\nD.Va")
    yield tmp_path
    settings.reload()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def test_parse_chaves_pt_e_en():
    parsed = sim.parse_sim_args("mapa=Ilios inimigos=Tracer,Winston aliados=Mei")
    assert parsed == {"map": ["Ilios"], "enemies": ["Tracer", "Winston"], "allies": ["Mei"]}
    parsed = sim.parse_sim_args("map=Ilios enemies=Tracer allies=Mei bans=Sombra")
    assert parsed is not None
    assert parsed["bans"] == ["Sombra"]


def test_parse_nomes_com_espaco():
    parsed = sim.parse_sim_args("inimigos=Junker Queen,Soldier 76 mapa=Route 66")
    assert parsed is not None
    assert parsed["enemies"] == ["Junker Queen", "Soldier 76"]
    assert parsed["map"] == ["Route 66"]


def test_parse_sem_chaves_reconhecidas_devolve_none():
    assert sim.parse_sim_args("qualquer coisa") is None
    assert sim.parse_sim_args("") is None


# ---------------------------------------------------------------------------
# Resolução fuzzy
# ---------------------------------------------------------------------------
def test_resolucao_fuzzy_de_herois():
    resolved = sim._resolve_heroes(["tracer", "junker quen", "dva"], echo=lambda _: None)
    assert resolved == ["Tracer", "Junker Queen", "D.Va"]


def test_heroi_irreconhecivel_e_avisado_e_ignorado():
    msgs: list[str] = []
    resolved = sim._resolve_heroes(["xyzk9"], echo=msgs.append)
    assert resolved == []
    assert any("xyzk9" in m for m in msgs)


def test_resolucao_de_mapa_com_alias_pt():
    assert sim._resolve_map(["ilios"], echo=lambda _: None) == "Ilios"
    assert sim._resolve_map(["Rota 66"], echo=lambda _: None) == "Route 66"
    msgs: list[str] = []
    assert sim._resolve_map(["zzzz"], echo=msgs.append) == "UNKNOWN"
    assert msgs  # aviso emitido


# ---------------------------------------------------------------------------
# Fluxo completo (apenas scoring — sem captura)
# ---------------------------------------------------------------------------
def test_executar_simulacao_completa(user_env, capsys):
    result = sim.executar("mapa=Ilios inimigos=Tracer,Winston aliados=Mei", echo=print)
    assert result is not None
    assert result.mapa == "Ilios"
    assert result.enemies == ["Tracer", "Winston"]
    assert result.allies == ["Mei"]
    # Só o scoring: recomendações vieram dos favoritos da role TANK.
    names = [r.hero.name for r in result.recommendations]
    assert set(names) == {"Zarya", "Winston", "D.Va"}  # inimigo NÃO é excluído (só aliado/ban)
    out = capsys.readouterr().out
    assert "Simulação: mapa=Ilios" in out
    assert "RANK" in out  # ranking renderizado


def test_executar_sem_role_orienta_usuario(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APPDATA", str(tmp_path / "vazio"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "vazio-local"))
    settings.reload()
    result = sim.executar("mapa=Ilios inimigos=Tracer")
    assert result is None
    assert "opção 2" in capsys.readouterr().out
    settings.reload()


def test_executar_uso_invalido_mostra_usage(user_env, capsys):
    assert sim.executar("blablabla") is None
    assert "Uso: sim" in capsys.readouterr().out
