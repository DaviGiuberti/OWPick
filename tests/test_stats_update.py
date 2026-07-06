"""Atualização de stats por DOWNLOAD do CSV publicado (sem deps externas)."""

from __future__ import annotations

import urllib.error
from contextlib import contextmanager

import pytest

from owpick import settings
from owpick.infra import datasource, stats_update

VALID_CSV = (
    b"map,map_type,map_slug,hero,role,winrate,pickrate\nIlios,control,ilios,Ana,SUP,52.0,8.0\n"
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    from owpick import paths

    paths.ensure_dirs()
    yield tmp_path
    settings.reload()


def _fake_urlopen(data: bytes):
    @contextmanager
    def _open(req, timeout=None):
        class _Resp:
            def read(self):
                return data

        yield _Resp()

    return _open


def test_download_sucesso_grava_override_e_invalida_cache(isolated, monkeypatch):
    monkeypatch.setattr(stats_update.urllib.request, "urlopen", _fake_urlopen(VALID_CSV))
    cleared = {"n": 0}
    monkeypatch.setattr(datasource, "refresh_stats_cache", lambda: cleared.__setitem__("n", 1))

    msgs: list[str] = []
    assert stats_update.update_stats(report=msgs.append) is True
    # Gravou no override do usuário e invalidou o cache.
    with open(datasource.user_stats_path(), "rb") as f:
        assert f.read() == VALID_CSV
    assert cleared["n"] == 1
    assert any("sucesso" in m.lower() for m in msgs)


def test_funciona_no_executavel_congelado(isolated, monkeypatch):
    """Não depende de código-fonte/Playwright: só download (stdlib)."""
    import sys as _sys

    monkeypatch.setattr(_sys, "frozen", True, raising=False)  # simula o .exe
    monkeypatch.setattr(stats_update.urllib.request, "urlopen", _fake_urlopen(VALID_CSV))
    monkeypatch.setattr(datasource, "refresh_stats_cache", lambda: None)
    assert stats_update.update_stats(report=lambda _: None) is True


def test_falha_de_rede_avisa_e_preserva_stats(isolated, monkeypatch):
    def _boom(req, timeout=None):
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(stats_update.urllib.request, "urlopen", _boom)
    msgs: list[str] = []
    assert stats_update.update_stats(report=msgs.append) is False
    # Não criou override; mensagem orienta o usuário.
    import os

    assert not os.path.exists(datasource.user_stats_path())
    assert any("conexão" in m.lower() or "internet" in m.lower() for m in msgs)


def test_csv_invalido_nao_sobrescreve(isolated, monkeypatch):
    # Pré-existe um override válido que NÃO pode ser corrompido.
    import os

    dest = datasource.user_stats_path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(VALID_CSV)

    monkeypatch.setattr(
        stats_update.urllib.request, "urlopen", _fake_urlopen(b"<html>404 Not Found</html>")
    )
    msgs: list[str] = []
    assert stats_update.update_stats(report=msgs.append) is False
    with open(dest, "rb") as f:
        assert f.read() == VALID_CSV  # intacto
    assert any("inválido" in m.lower() for m in msgs)


def test_url_override_do_settings(isolated, monkeypatch):
    settings.save(settings.Settings(stats_url="https://exemplo.test/stats.csv"))
    captured = {}

    @__import__("contextlib").contextmanager
    def _capture(req, timeout=None):
        captured["url"] = req.full_url

        class _Resp:
            def read(self):
                return VALID_CSV

        yield _Resp()

    monkeypatch.setattr(stats_update.urllib.request, "urlopen", _capture)
    monkeypatch.setattr(datasource, "refresh_stats_cache", lambda: None)
    assert stats_update.update_stats(report=lambda _: None) is True
    assert captured["url"] == "https://exemplo.test/stats.csv"


def test_validacao_de_csv():
    assert stats_update._validate_csv(VALID_CSV) is None
    assert stats_update._validate_csv(b"foo,bar\n1,2\n") is not None  # faltam colunas
    assert stats_update._validate_csv(b"not a csv at all \x00\x01") is not None


def test_datasource_prefere_override_do_usuario(monkeypatch, tmp_path):
    """stats_source_path usa o override do usuário quando ele existe."""
    override = tmp_path / "stats_inputs.csv"
    monkeypatch.setattr(datasource, "user_stats_path", lambda: str(override))
    assert datasource.stats_source_path() != str(override)
    override.write_text("map,role\n", encoding="utf-8")
    assert datasource.stats_source_path() == str(override)
