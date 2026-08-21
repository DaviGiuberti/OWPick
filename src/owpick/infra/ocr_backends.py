"""ocr_backends.py — Backends de OCR plugáveis (camada infra).

O map_detect faz o pré-processamento da imagem (crop/grayscale/autocontraste/
upscale) e delega o reconhecimento de texto a `run_ocr(img)`, que despacha para
o backend selecionado. Hoje há dois backends:

  - "tesseract" (PADRÃO): Tesseract embutido em assets/ocr/ (subprocesso). É o
    backend validado; permanece o padrão.
  - "windows"  (OPCIONAL/EXPERIMENTAL): API nativa Windows.Media.Ocr via `winsdk`
    (in-process, sem subprocesso e sem os ~dezenas de MB do Tesseract no bundle).
    Requer o pacote `winsdk` (grupo opcional `ocr-win` do pyproject) E um language
    pack do idioma no Windows. Dorme se `winsdk` não estiver instalado.

Seleção via env `OWPICK_OCR_BACKEND` (= "tesseract" | "windows"; default
"tesseract"). Se "windows" for pedido mas indisponível, cai para "tesseract".

Por que ainda não é o padrão (tarefa 4.5): a troca só é segura se a acurácia na
FONTE ESTILIZADA do jogo não regredir — isso precisa ser medido com as fixtures
(tarefa 1.4) numa máquina com `winsdk` + language pack. Enquanto essa medição não
aprovar, o Tesseract continua sendo o backend padrão (requisito da tarefa: "se a
acurácia regredir, não remover o Tesseract ainda"). Este seam existe justamente
para tornar essa avaliação trivial (basta instalar `ocr-win` e setar a env).
"""

from __future__ import annotations

import os

from PIL import Image

from owpick.infra.resources import resource_path
from owpick.log import get_logger

log = get_logger("ocr")

try:
    import pytesseract
except Exception:  # noqa: BLE001 — OCR é opcional; degrada para "" (UNKNOWN)
    pytesseract = None

# Caminho do Tesseract embutido (assets/ocr/) — resolvido para .py e .exe.
_TESSERACT_EXE = resource_path(os.path.join("assets", "ocr", "tesseract.exe"))
_TESSDATA_DIR = resource_path(os.path.join("assets", "ocr", "tessdata"))

ENV_BACKEND = "OWPICK_OCR_BACKEND"
DEFAULT_BACKEND = "tesseract"

# Modo de segmentacao de pagina do Tesseract (--psm) usado por padrao: 7 = trata
# a imagem como UMA linha de texto, que e o formato dos dois recortes do OWPick
# (nome do mapa e nome do heroi). Os chamadores podem pedir outro modo — o
# player_hero recorre ao 11 (texto esparso) quando a leitura padrao falha.
DEFAULT_PSM = 7
SPARSE_PSM = 11


# ---------------------------------------------------------------------------
# Backend: Tesseract (padrão, validado)
# ---------------------------------------------------------------------------
def _configure_tesseract() -> bool:
    """Aponta o pytesseract para o Tesseract embutido. False se indisponível."""
    if pytesseract is None:
        return False
    if os.path.exists(_TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE
    # TESSDATA_PREFIX evita passar --tessdata-dir (que corrompe caminhos com
    # espaços/aspas e quebra o carregamento do idioma).
    if os.path.isdir(_TESSDATA_DIR):
        os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR
    return True


def tesseract_ocr(img: Image.Image, psm: int = DEFAULT_PSM) -> str:
    """OCR via Tesseract embutido. '' em caso de falha.

    `psm` = modo de segmentação de página (--psm); DEFAULT_PSM (7, linha única) é
    o padrão dos dois recortes do OWPick.
    """
    if not _configure_tesseract() or pytesseract is None:
        return ""
    return pytesseract.image_to_string(img, lang="eng", config=f"--oem 3 --psm {psm}").strip()


# ---------------------------------------------------------------------------
# Backend: Windows.Media.Ocr (opcional/experimental via winsdk)
# ---------------------------------------------------------------------------
def windows_ocr_available() -> bool:
    """True se o `winsdk` (projeção Windows.Media.Ocr) estiver importável."""
    try:
        import winsdk.windows.media.ocr  # noqa: F401  # pyright: ignore[reportMissingImports]
    except Exception:  # noqa: BLE001
        return False
    return True


def windows_ocr(img: Image.Image) -> str:
    """
    OCR in-process via Windows.Media.Ocr (winsdk). EXPERIMENTAL — não é o padrão
    e não foi validado na fonte do jogo (ver docstring do módulo). '' se o winsdk
    ou o language pack não estiverem disponíveis.
    """
    try:
        import asyncio

        from winsdk.windows.globalization import (  # pyright: ignore[reportMissingImports]
            Language,
        )
        from winsdk.windows.graphics.imaging import (  # pyright: ignore[reportMissingImports]
            BitmapAlphaMode,
            BitmapPixelFormat,
            SoftwareBitmap,
        )
        from winsdk.windows.media.ocr import (  # pyright: ignore[reportMissingImports]
            OcrEngine,
        )
        from winsdk.windows.security.cryptography import (  # pyright: ignore[reportMissingImports]
            CryptographicBuffer,
        )

        engine = OcrEngine.try_create_from_language(Language("en-US"))
        if engine is None:
            engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            log.warning("Windows OCR: nenhum language pack disponível")
            return ""

        rgba = img.convert("RGBA")
        w, h = rgba.size
        buf = CryptographicBuffer.create_from_byte_array(rgba.tobytes())
        bitmap = SoftwareBitmap.create_copy_from_buffer(
            buf, BitmapPixelFormat.RGBA8, w, h, BitmapAlphaMode.PREMULTIPLIED
        )

        async def _recognize() -> str:
            result = await engine.recognize_async(bitmap)
            return result.text or ""

        return asyncio.run(_recognize()).strip()
    except Exception:  # noqa: BLE001 — degrada para "" (o dispatcher cai p/ Tesseract)
        log.warning("Windows OCR falhou", exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def selected_backend() -> str:
    """Backend efetivo: env OWPICK_OCR_BACKEND, com fallback para tesseract se o
    Windows OCR for pedido mas estiver indisponível."""
    choice = os.environ.get(ENV_BACKEND, DEFAULT_BACKEND).strip().lower()
    if choice == "windows" and not windows_ocr_available():
        log.warning("OCR backend 'windows' indisponível (winsdk ausente) — usando tesseract")
        return "tesseract"
    return choice if choice in ("tesseract", "windows") else "tesseract"


def run_ocr(img: Image.Image, psm: int = DEFAULT_PSM) -> str:
    """Roda o OCR no backend selecionado. '' em caso de falha (→ UNKNOWN).

    `psm` só tem efeito no Tesseract: o Windows.Media.Ocr não expõe um controle
    equivalente de segmentação de página (faz o próprio layout analysis), então
    o parâmetro é ignorado nesse backend.
    """
    backend = selected_backend()
    if backend == "windows":
        return windows_ocr(img)
    return tesseract_ocr(img, psm=psm)
