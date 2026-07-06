"""Testes dos menus de console por injeção de input (2.8).

Os menus (roles/favorites) e o prompt do updater aceitam uma fonte de input
injetável, com default real (msvcrt.getch/input). Aqui passamos stubs para
exercitar o fluxo sem teclado — sem mudar o comportamento de produção.
"""

from owpick.infra import storage, updater
from owpick.ui import favorites, roles


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from owpick import paths

    paths.ensure_dirs()


def test_roles_executar_grava_role(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # Stub de tecla: escolhe "4" -> DPS.
    role = roles.executar(read_key=lambda: "4")
    assert role == "DPS"
    assert storage.read_role() == "DPS"


def test_roles_ignora_teclas_invalidas_ate_valida(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    keys = iter(["x", "9", "\x00", "2"])  # só "2" (=TANK) é válida
    role = roles.executar(read_key=lambda: next(keys))
    assert role == "TANK"


def test_favorites_add_e_sair(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # Sequência: 1 (add) -> "tracer" -> 5 (sair)
    answers = iter(["1", "tracer", "5"])
    favorites.executar(ask=lambda _prompt: next(answers))
    assert "Tracer" in storage.load_favorites()


def test_favorites_add_lote_por_funcao(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    # 4 (add função) -> submenu "1" (DPS) -> 5 (sair)
    answers = iter(["4", "1", "5"])
    favorites.executar(ask=lambda _prompt: next(answers))
    favs = storage.load_favorites()
    # Todos os DPS entram (ex.: Tracer, Genji estão na role DPS).
    assert "Tracer" in favs and "Genji" in favs


def test_updater_declina_nao_aplica(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_fetch_version_info",
        lambda: {"version": "99.0.0", "download_url": "x", "notas": ""},
    )
    called = []
    monkeypatch.setattr(updater, "_apply_update", lambda url: called.append(url))
    updater.check_for_updates(ask=lambda _prompt: "n")
    assert called == []  # usuário recusou -> nada aplicado


def test_updater_aceita_aplica(monkeypatch):
    monkeypatch.setattr(
        updater,
        "_fetch_version_info",
        lambda: {"version": "99.0.0", "download_url": "http://x/pkg.zip", "notas": "nova"},
    )
    called = []
    monkeypatch.setattr(updater, "_apply_update", lambda url: called.append(url))
    updater.check_for_updates(ask=lambda _prompt: "s")
    assert called == ["http://x/pkg.zip"]
