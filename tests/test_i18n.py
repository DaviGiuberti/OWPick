"""Testes das strings de UI centralizadas por idioma (tarefa 6.6)."""

import json

import pytest

from owpick import settings
from owpick.i18n import DEFAULT_LANGUAGE, _load, t
from owpick.infra.resources import resource_path


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    yield tmp_path
    settings.reload()


def test_pt_br_default(isolated_settings):
    assert "Role" in t("pipeline.role_missing")
    assert "opção 2" in t("pipeline.role_missing")  # "o que fazer" presente


def test_ingles_quando_language_en(isolated_settings):
    settings.save(settings.Settings(language="en"))
    assert t("ranking.map", map="Ilios") == "Current map: Ilios"
    assert "menu option 2" in t("pipeline.role_missing")


def test_placeholders_formatados(isolated_settings):
    assert t("boot.hotkey_hint", hotkey="CTRL+F9").strip().startswith("- Pressione CTRL+F9")


def test_chave_desconhecida_devolve_a_chave(isolated_settings):
    assert t("nao.existe") == "nao.existe"


def test_tabelas_pt_e_en_tem_as_mesmas_chaves():
    """Nenhuma chave pode existir só num idioma (evita EN cair no pt sem aviso)."""
    pt = set(_load("pt-BR"))
    en = set(_load("en"))
    assert pt and pt == en


def test_arquivos_json_validos_no_repo():
    for lang in (DEFAULT_LANGUAGE, "en"):
        with open(resource_path(f"assets/i18n/{lang}.json"), encoding="utf-8") as f:
            assert isinstance(json.load(f), dict)
