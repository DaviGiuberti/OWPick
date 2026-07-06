"""Testes da captura da janela do jogo / fallback ao monitor (tarefa 4.3)."""

from __future__ import annotations

from PIL import Image

from owpick.infra import capture


class _FakeGrab:
    def __init__(self, img: Image.Image):
        self.size = img.size
        self.rgb = img.convert("RGB").tobytes()


class _FakeSct:
    """mss falso que REGISTRA o monitor pedido no grab()."""

    def __init__(self, img: Image.Image):
        self._img = img
        self.monitors = [{"desc": "all"}, {"desc": "primary", "left": 0, "top": 0}]
        self.grabbed: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, monitor):
        self.grabbed = monitor
        return _FakeGrab(self._img)


class _FakeMss:
    def __init__(self, sct: _FakeSct):
        self._sct = sct

    def mss(self):
        return self._sct


def test_grab_usa_janela_do_overwatch_quando_encontrada(monkeypatch):
    img = Image.new("RGB", (1920, 1080), (10, 20, 30))
    sct = _FakeSct(img)
    monkeypatch.setattr(capture, "mss", _FakeMss(sct))
    rect = {"left": 100, "top": 50, "width": 1920, "height": 1080}
    monkeypatch.setattr(capture, "find_overwatch_client_rect", lambda: rect)

    out = capture.grab_screen()
    assert out.size == (1920, 1080)
    assert sct.grabbed == rect  # capturou o retângulo do cliente, não o monitor


def test_grab_cai_para_monitor_primario_sem_janela(monkeypatch):
    img = Image.new("RGB", (1280, 720), (0, 0, 0))
    sct = _FakeSct(img)
    monkeypatch.setattr(capture, "mss", _FakeMss(sct))
    monkeypatch.setattr(capture, "find_overwatch_client_rect", lambda: None)

    capture.grab_screen()
    assert sct.grabbed is sct.monitors[1]  # fallback: monitor primário


def test_find_client_rect_sem_win32_retorna_none(monkeypatch):
    """Sem windll (não-Windows) a busca degrada para None, sem lançar."""
    monkeypatch.delattr(capture.ctypes, "windll", raising=False)
    assert capture.find_overwatch_client_rect() is None
