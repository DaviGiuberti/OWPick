"""Testes de owpick.paths — separação dos três tipos de dado e migração (2.6)."""

import os

from owpick import paths


def _isolate(monkeypatch, tmp_path):
    """Aponta APPDATA/LOCALAPPDATA para diretórios temporários isolados."""
    appdata = tmp_path / "AppData" / "Roaming"
    localappdata = tmp_path / "AppData" / "Local"
    appdata.mkdir(parents=True)
    localappdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    return appdata, localappdata


def test_dirs_separam_os_tres_tipos(monkeypatch, tmp_path):
    appdata, localappdata = _isolate(monkeypatch, tmp_path)
    assert paths.user_data_dir() == os.path.join(str(appdata), "OWPick")
    assert paths.cache_dir() == os.path.join(str(localappdata), "OWPick", "cache")
    assert paths.logs_dir() == os.path.join(str(appdata), "OWPick", "logs")
    # config/dados do usuário e temporários/debug NÃO compartilham raiz.
    assert not paths.cache_dir().startswith(paths.user_data_dir())


def test_ensure_dirs_cria_estrutura(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    paths.ensure_dirs()
    assert os.path.isdir(paths.user_data_dir())
    assert os.path.isdir(paths.logs_dir())
    assert os.path.isdir(paths.cache_dir())


def test_migracao_copia_dados_antigos(monkeypatch, tmp_path):
    """Primeira execução com Roles.txt/favoritos ao lado do exe -> migrados."""
    _isolate(monkeypatch, tmp_path)
    legacy = tmp_path / "old_install"
    legacy.mkdir()
    (legacy / "Roles.txt").write_text("DPS", encoding="utf-8")
    (legacy / "ALL.txt").write_text("Tracer\nGenji", encoding="utf-8")

    migrated = paths.migrate_legacy_user_data(legacy_dirs=[str(legacy)])

    assert set(migrated) == {"Roles.txt", "ALL.txt"}
    assert (tmp_path / "AppData" / "Roaming" / "OWPick" / "Roles.txt").read_text(
        encoding="utf-8"
    ) == "DPS"
    assert (tmp_path / "AppData" / "Roaming" / "OWPick" / "ALL.txt").read_text(
        encoding="utf-8"
    ) == "Tracer\nGenji"


def test_migracao_nao_sobrescreve_dados_existentes(monkeypatch, tmp_path):
    """Se já houver dado novo, a migração NÃO o substitui (nada é perdido)."""
    _isolate(monkeypatch, tmp_path)
    paths.ensure_dirs()
    # Dado já presente no local novo.
    novo = paths.user_file("Roles.txt")
    with open(novo, "w", encoding="utf-8") as f:
        f.write("SUP")

    legacy = tmp_path / "old_install"
    legacy.mkdir()
    (legacy / "Roles.txt").write_text("DPS", encoding="utf-8")

    migrated = paths.migrate_legacy_user_data(legacy_dirs=[str(legacy)])

    assert "Roles.txt" not in migrated
    with open(novo, encoding="utf-8") as f:
        assert f.read() == "SUP"  # preservado


def test_migracao_idempotente(monkeypatch, tmp_path):
    """Rodar a migração duas vezes não duplica nem falha."""
    _isolate(monkeypatch, tmp_path)
    legacy = tmp_path / "old_install"
    legacy.mkdir()
    (legacy / "Roles.txt").write_text("TANK", encoding="utf-8")

    first = paths.migrate_legacy_user_data(legacy_dirs=[str(legacy)])
    second = paths.migrate_legacy_user_data(legacy_dirs=[str(legacy)])

    assert first == ["Roles.txt"]
    assert second == []  # nada mais a migrar
