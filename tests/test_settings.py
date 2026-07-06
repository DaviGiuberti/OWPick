"""Testes do settings.json tipado e validado (tarefa 6.1)."""

import json

import pytest

from owpick import settings


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Aponta %APPDATA% para um tmp e invalida o cache do settings."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    yield tmp_path
    settings.reload()


def test_defaults_quando_arquivo_ausente(isolated_settings):
    cfg, problems = settings.load()
    assert problems == []
    assert cfg == settings.Settings()
    assert cfg.hotkey == ["tab", "1"]
    assert cfg.language == "pt-BR"
    assert cfg.debug is False
    # Overrides avançados desligados por padrão (usa a calibração dos módulos).
    assert cfg.lineup_match_max_score is None
    assert cfg.ban_match_max_score is None
    assert cfg.map_min_confidence is None
    assert cfg.updater_url is None


def test_roundtrip_save_load(isolated_settings):
    cfg = settings.Settings(hotkey=["ctrl", "f9"], language="en", debug=True)
    cfg.ban_match_max_score = 0.2
    settings.save(cfg)
    loaded, problems = settings.load()
    assert problems == []
    assert loaded == cfg
    # get() cacheado devolve o que foi salvo (save invalida o cache).
    assert settings.get() == cfg


def test_campo_invalido_cai_para_default_com_aviso(isolated_settings):
    cfg, problems = settings.parse(
        {
            "hotkey": [],  # inválido: lista vazia
            "language": "fr",  # inválido: idioma não suportado
            "debug": "sim",  # inválido: não é bool
            "ban_match_max_score": -1,  # inválido: <= 0
            "map_min_confidence": 40,  # válido (int > 0 vira float)
        }
    )
    assert cfg.hotkey == ["tab", "1"]
    assert cfg.language == "pt-BR"
    assert cfg.debug is False
    assert cfg.ban_match_max_score is None
    assert cfg.map_min_confidence == 40.0
    assert len(problems) == 4  # um aviso por campo inválido


def test_chave_desconhecida_ignorada_com_aviso(isolated_settings):
    cfg, problems = settings.parse({"tema": "escuro", "language": "en"})
    assert cfg.language == "en"
    assert any("tema" in p for p in problems)


def test_json_corrompido_usa_defaults(isolated_settings):
    path = settings.settings_path()
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ nada disso é json")
    cfg, problems = settings.load()
    assert cfg == settings.Settings()
    assert problems  # problema reportado, sem exceção


def test_arquivo_salvo_tem_version(isolated_settings):
    settings.save(settings.Settings())
    with open(settings.settings_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == settings.SETTINGS_VERSION


def test_override_de_limiar_do_lineup_e_aplicado(isolated_settings):
    """O matching usa o override do settings quando definido."""
    from owpick.infra import matching

    # Sem override: limiar calibrado do módulo.
    assert settings.get().lineup_match_max_score is None
    settings.save(settings.Settings(lineup_match_max_score=0.05))
    assert settings.get().lineup_match_max_score == 0.05
    # O default calibrado permanece intocado no módulo dono.
    assert matching.LINEUP_MATCH_MAX_SCORE == 0.70
