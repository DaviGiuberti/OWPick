"""Testes do seam de backends de OCR (tarefa 4.5)."""

from __future__ import annotations

import pytest

from owpick.infra import ocr_backends


def test_default_backend_e_tesseract(monkeypatch):
    monkeypatch.delenv(ocr_backends.ENV_BACKEND, raising=False)
    assert ocr_backends.selected_backend() == "tesseract"


def test_valor_invalido_cai_para_tesseract(monkeypatch):
    monkeypatch.setenv(ocr_backends.ENV_BACKEND, "xpto")
    assert ocr_backends.selected_backend() == "tesseract"


def test_windows_pedido_mas_indisponivel_cai_para_tesseract(monkeypatch):
    monkeypatch.setenv(ocr_backends.ENV_BACKEND, "windows")
    monkeypatch.setattr(ocr_backends, "windows_ocr_available", lambda: False)
    assert ocr_backends.selected_backend() == "tesseract"


def test_run_ocr_despacha_para_backend_selecionado(monkeypatch):
    monkeypatch.setenv(ocr_backends.ENV_BACKEND, "windows")
    monkeypatch.setattr(ocr_backends, "windows_ocr_available", lambda: True)
    monkeypatch.setattr(ocr_backends, "windows_ocr", lambda img: "WINDOWS")
    monkeypatch.setattr(ocr_backends, "tesseract_ocr", lambda img: "TESS")
    assert ocr_backends.run_ocr(object()) == "WINDOWS"  # type: ignore[arg-type]


@pytest.mark.skipif(
    not ocr_backends.windows_ocr_available(), reason="winsdk não instalado (grupo ocr-win)"
)
def test_windows_ocr_reconhece_texto():
    """Só roda se o winsdk estiver presente — smoke do backend nativo."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (240, 60), (255, 255, 255))
    ImageDraw.Draw(img).text((10, 15), "ILIOS", fill=(0, 0, 0))
    text = ocr_backends.windows_ocr(img)
    assert "ILIOS" in text.upper()
