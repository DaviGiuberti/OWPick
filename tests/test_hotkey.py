"""Testes da hotkey de captura configurável (tarefa 6.2).

É a "forma de testar que a captura de hotkey funciona": detector, captura em
tempo real e persistência são exercitados com eventos/entradas sintéticos —
nenhum teclado real envolvido.
"""

from types import SimpleNamespace

import pytest

from owpick import settings
from owpick.ui import hotkey


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    yield tmp_path
    settings.reload()


def _ev(event_type: str, name: str):
    return SimpleNamespace(event_type=event_type, name=name)


# ---------------------------------------------------------------------------
# HotkeyDetector — mesma semântica do antigo TAB+1
# ---------------------------------------------------------------------------
def test_detector_dispara_com_modificador_seguro():
    fired = []
    det = hotkey.HotkeyDetector(["tab", "1"], lambda: fired.append(1))
    assert det.handle("down", "tab") is False
    assert det.handle("down", "1") is True
    assert fired == [1]


def test_detector_nao_dispara_sem_modificador():
    fired = []
    det = hotkey.HotkeyDetector(["tab", "1"], lambda: fired.append(1))
    assert det.handle("down", "1") is False  # "1" sozinho (digitação no menu)
    det.handle("down", "tab")
    det.handle("up", "tab")  # TAB solto antes do "1"
    assert det.handle("down", "1") is False
    assert fired == []


def test_detector_combo_arbitrario():
    fired = []
    det = hotkey.HotkeyDetector(["ctrl", "shift", "f9"], lambda: fired.append(1))
    det.handle("down", "ctrl")
    assert det.handle("down", "f9") is False  # falta o shift
    det.handle("down", "shift")
    assert det.handle("down", "f9") is True
    assert fired == [1]


# ---------------------------------------------------------------------------
# Captura em tempo real
# ---------------------------------------------------------------------------
def test_capture_combo_exibe_em_tempo_real_e_finaliza_ao_soltar():
    events = iter(
        [
            _ev("down", "ctrl"),
            _ev("down", "f9"),
            _ev("up", "f9"),
            _ev("up", "ctrl"),
        ]
    )
    shown: list[str] = []
    combo = hotkey.capture_combo(read_event=lambda: next(events), echo=shown.append)
    assert combo == ["ctrl", "f9"]
    # Feedback em tempo real: a combinação parcial aparece a cada tecla nova.
    assert any("CTRL" in s for s in shown)
    assert any("CTRL+F9" in s for s in shown)


def test_validate_combo_rejeita_tecla_unica_de_digitacao():
    assert hotkey.validate_combo(["a"]) is not None
    assert hotkey.validate_combo([]) is not None
    assert hotkey.validate_combo(["ctrl", "f9"]) is None
    assert hotkey.validate_combo(["f8"]) is None  # tecla de função sozinha ok


# ---------------------------------------------------------------------------
# Menu: confirmar nova combinação / voltar ao padrão (persistência)
# ---------------------------------------------------------------------------
def test_executar_captura_confirma_e_persiste(isolated_settings):
    events = iter([_ev("down", "ctrl"), _ev("down", "f9"), _ev("up", "f9"), _ev("up", "ctrl")])
    answers = iter(["1", "s"])  # capturar nova -> confirmar
    result = hotkey.executar(ask=lambda _: next(answers), read_event=lambda: next(events))
    assert result == ["ctrl", "f9"]
    assert settings.get().hotkey == ["ctrl", "f9"]


def test_executar_recusa_mantem_hotkey(isolated_settings):
    events = iter([_ev("down", "ctrl"), _ev("down", "f9"), _ev("up", "f9"), _ev("up", "ctrl")])
    answers = iter(["1", "n"])  # capturar nova -> recusar
    result = hotkey.executar(ask=lambda _: next(answers), read_event=lambda: next(events))
    assert result is None
    assert settings.get().hotkey == ["tab", "1"]


def test_executar_volta_ao_padrao(isolated_settings):
    settings.save(settings.Settings(hotkey=["ctrl", "f9"]))
    result = hotkey.executar(ask=lambda _: "2")
    assert result == ["tab", "1"]
    assert settings.get().hotkey == ["tab", "1"]
