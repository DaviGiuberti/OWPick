"""Testes de múltiplos perfis (tarefa 6.8)."""

import pytest

from owpick import settings
from owpick.infra import storage
from owpick.ui import profiles


@pytest.fixture
def user_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    from owpick import paths

    paths.ensure_dirs()
    yield tmp_path
    settings.reload()


def _setup_state(role: str, favorites: list[str], preset: str) -> None:
    from owpick.core.heroes import get_hero_role

    storage.write_role(role)
    storage.save_heroes_to_files(favorites, get_hero_role)
    cfg = settings.get()
    cfg.weights_preset = preset
    settings.save(cfg)


def test_salvar_e_trocar_perfil_aplica_role_favoritos_e_preset(user_env):
    # Perfil 1: TANK / counter-first.
    _setup_state("TANK", ["Zarya", "Winston"], "counter-first")
    profiles.save_profile("ranqueada")

    # Perfil 2: DPS / conforto+.
    _setup_state("DPS", ["Tracer", "Ashe"], "conforto+")
    profiles.save_profile("casual")
    assert settings.get().active_profile == "casual"

    # Troca de volta para o perfil 1 — tudo aplicado pelos mecanismos existentes.
    assert profiles.apply_profile("ranqueada") is True
    assert storage.read_role() == "TANK"
    assert storage.load_favorites() == ["Zarya", "Winston"]
    cfg = settings.get()
    assert cfg.weights_preset == "counter-first"
    assert cfg.active_profile == "ranqueada"


def test_perfil_inexistente_nao_aplica(user_env):
    assert profiles.apply_profile("nao-existe") is False


def test_remover_perfil(user_env):
    _setup_state("SUP", ["Ana"], "equilibrado")
    profiles.save_profile("suporte")
    assert profiles.delete_profile("suporte") is True
    assert settings.get().active_profile is None
    assert profiles.delete_profile("suporte") is False


def test_perfis_persistem_no_settings_json(user_env):
    _setup_state("DPS", ["Tracer"], "meta-first")
    profiles.save_profile("meu")
    settings.reload()  # relê do disco
    cfg = settings.get()
    assert "meu" in cfg.profiles
    assert cfg.profiles["meu"].role == "DPS"
    assert cfg.profiles["meu"].favorites == ["Tracer"]
    assert cfg.profiles["meu"].weights_preset == "meta-first"


def test_validacao_descarta_perfil_invalido_preserva_validos():
    cfg, problems = settings.parse(
        {
            "profiles": {
                "ok": {"role": "DPS", "favorites": ["Tracer"], "weights_preset": "equilibrado"},
                "ruim": {"role": "JUNGLER"},  # role inválida
            }
        }
    )
    assert "ok" in cfg.profiles
    assert "ruim" not in cfg.profiles
    assert any("ruim" in p for p in problems)


def test_menu_executar_com_input_injetado(user_env):
    _setup_state("TANK", ["Zarya"], "equilibrado")
    answers = iter(["1", "principal", "4"])  # salvar como "principal" -> sair
    profiles.executar(ask=lambda _: next(answers))
    assert "principal" in settings.get().profiles
