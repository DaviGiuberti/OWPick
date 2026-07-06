"""Atualização de stats a partir do app (tarefa 5.3)."""

from __future__ import annotations

from owpick.infra import datasource, stats_update


def test_frozen_avisa_e_nao_roda(monkeypatch):
    monkeypatch.setattr(stats_update.sys, "frozen", True, raising=False)
    msgs: list[str] = []
    assert stats_update.update_stats(report=msgs.append) is False
    assert any("executável" in m.lower() for m in msgs)


def test_sem_playwright_da_instrucao_clara(monkeypatch):
    monkeypatch.setattr(stats_update.sys, "frozen", False, raising=False)
    monkeypatch.setattr(stats_update, "_scraper_script", lambda: __file__ and _fake_path())
    monkeypatch.setattr(stats_update, "_playwright_available", lambda: False)
    msgs: list[str] = []
    assert stats_update.update_stats(report=msgs.append) is False
    assert any("playwright" in m.lower() for m in msgs)


def _fake_path():
    from pathlib import Path

    return Path(__file__)


def test_sucesso_invalida_cache_e_reporta(monkeypatch, tmp_path):
    monkeypatch.setattr(stats_update.sys, "frozen", False, raising=False)
    monkeypatch.setattr(stats_update, "_scraper_script", lambda: tmp_path / "scraper.py")
    (tmp_path / "scraper.py").write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(stats_update, "_playwright_available", lambda: True)
    monkeypatch.setattr(datasource, "user_stats_path", lambda: str(tmp_path / "stats_inputs.csv"))

    class _Proc:
        returncode = 0

    monkeypatch.setattr(stats_update.subprocess, "run", lambda *a, **k: _Proc())
    cleared = {"n": 0}
    monkeypatch.setattr(datasource, "refresh_stats_cache", lambda: cleared.__setitem__("n", 1))

    msgs: list[str] = []
    assert stats_update.update_stats(report=msgs.append) is True
    assert cleared["n"] == 1
    assert any("sucesso" in m.lower() for m in msgs)


def test_datasource_prefere_override_do_usuario(monkeypatch, tmp_path):
    """stats_source_path usa o override do usuário quando ele existe."""
    override = tmp_path / "stats_inputs.csv"
    monkeypatch.setattr(datasource, "user_stats_path", lambda: str(override))
    # sem override -> caminho embutido
    assert datasource.stats_source_path() != str(override)
    override.write_text("map,role\n", encoding="utf-8")
    assert datasource.stats_source_path() == str(override)
