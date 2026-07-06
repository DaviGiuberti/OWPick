"""Menu de troca de preset de pesos, vinculado ao perfil (mudança pós-6.x)."""

import pytest

from owpick import settings
from owpick.core.scoring import PRESETS
from owpick.ui import profiles, weights


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    from owpick import paths

    paths.ensure_dirs()
    yield tmp_path
    settings.reload()


def test_set_weights_preset_sem_perfil(isolated):
    profiles.set_weights_preset("counter-first")
    assert settings.get().weights_preset == "counter-first"


def test_set_weights_preset_vincula_ao_perfil_ativo(isolated):
    from owpick.core.heroes import get_hero_role
    from owpick.infra import storage

    storage.write_role("TANK")
    storage.save_heroes_to_files(["Zarya"], get_hero_role)
    profiles.save_profile("ranqueada")  # vira o perfil ativo, preset "equilibrado"

    profiles.set_weights_preset("meta-first")
    cfg = settings.get()
    assert cfg.weights_preset == "meta-first"
    # A escolha ACOMPANHA o perfil: gravada dentro dele.
    assert cfg.profiles["ranqueada"].weights_preset == "meta-first"


def test_preset_persiste_ao_alternar_perfis(isolated):
    from owpick.core.heroes import get_hero_role
    from owpick.infra import storage

    storage.write_role("TANK")
    storage.save_heroes_to_files(["Zarya"], get_hero_role)
    profiles.save_profile("A")
    storage.write_role("DPS")
    storage.save_heroes_to_files(["Tracer"], get_hero_role)
    profiles.save_profile("B")

    # Vincula counter-first ao perfil ativo B, troca para A e volta para B.
    profiles.set_weights_preset("counter-first")
    profiles.apply_profile("A")
    assert settings.get().weights_preset == "equilibrado"
    profiles.apply_profile("B")
    assert settings.get().weights_preset == "counter-first"


def test_menu_escolhe_preset_por_numero(isolated):
    order = list(PRESETS)
    idx_counter = order.index("counter-first") + 1
    chosen = weights.executar(ask=lambda _: str(idx_counter))
    assert chosen == "counter-first"
    assert settings.get().weights_preset == "counter-first"


def test_menu_cancela_sem_alterar(isolated):
    order = list(PRESETS)
    cancel = str(len(order) + 1)
    assert weights.executar(ask=lambda _: cancel) is None
    assert settings.get().weights_preset == "equilibrado"


def test_menu_opcao_invalida(isolated):
    assert weights.executar(ask=lambda _: "99") is None
    assert weights.executar(ask=lambda _: "abc") is None
    assert settings.get().weights_preset == "equilibrado"
