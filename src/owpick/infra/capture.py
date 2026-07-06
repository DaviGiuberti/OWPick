"""capture.py — Captura da tela e recorte dos retratos EM MEMÓRIA.

Camada infra (implementa o protocolo core.ports.ScreenCapturer). O pipeline
consome o CaptureResult; nada é escrito em disco no caminho normal. Os PNGs de
print/ passam a ser apenas artefatos de debug (save_debug_artifacts).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os

import mss
from PIL import Image

from owpick import paths
from owpick.core import resolution
from owpick.core.models import CaptureResult
from owpick.infra import datasource, storage
from owpick.log import get_logger

log = get_logger("capture")

# Título exato da janela do cliente do Overwatch (todos os idiomas usam este).
OVERWATCH_WINDOW_TITLE = "Overwatch"
# Aspect ratio suportado: SOMENTE 16:9. Não há suporte a ultrawide (21:9) nem a
# outros formatos — a geometria dos layouts assume 16:9 (ver README/docs).
_ASPECT_16_9 = 16 / 9
_ASPECT_TOLERANCE = 0.05  # ~5% de folga para bordas/arredondamento

# As coordenadas de captura NÃO são mais hardcoded: vivem no layout versionado
# data/layouts/ow_hero_select.json (lido via datasource.load_layout). O código
# aqui apenas INTERPRETA o layout e aplica a mesma matemática de escala
# (resolution.scale_and_clamp) da região do mapa. Fallback base 720p só é usado
# se o layout estiver ausente (nunca deveria, é empacotado).
_FALLBACK_BASE = (1280, 720)

DEBUG_SUBDIR = "print"  # subpasta dos artefatos de debug dentro do cache


def debug_dir() -> str:
    """Destino dos artefatos de debug: %LOCALAPPDATA%\\OWPick\\cache\\print."""
    return paths.cache_file(DEBUG_SUBDIR)


def _skip_files_for_role(role: str | None) -> set[str]:
    """Slot do PRÓPRIO jogador, que não deve entrar na lista de aliados."""
    if role == "DPS":
        return {"ally2.png"}
    if role == "SUP":
        return {"ally4.png"}
    if role in ("TANK", "ALL"):
        return {"ally1.png"}
    return set()


def find_overwatch_client_rect() -> dict[str, int] | None:
    """
    Localiza a janela do Overwatch via Win32 e devolve o retângulo do CLIENTE
    (área útil, sem bordas/barra de título) como um dict no formato do mss
    ({"left", "top", "width", "height"}), em coordenadas de tela.

    Retorna None se a janela não existir, estiver minimizada, ou o Win32 não
    estiver disponível — nesse caso o chamador cai para o monitor primário. Isso
    dá suporte a multi-monitor e ao modo janela (a escala passa a ser calculada
    sobre o tamanho real do cliente, não sobre o monitor inteiro).
    """
    user32 = getattr(ctypes, "windll", None)
    if user32 is None:  # não-Windows: sem Win32
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, OVERWATCH_WINDOW_TITLE)
        if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return None

        rect = ctypes.wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None

        # Converte a origem do cliente (0,0) para coordenadas de tela.
        point = ctypes.wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
            return None

        aspect = width / height
        if abs(aspect - _ASPECT_16_9) > _ASPECT_TOLERANCE:
            # 16:9 é o único formato suportado. Não abortamos (a captura ainda
            # roda), mas o alinhamento dos recortes pode não bater — avisamos.
            log.warning(
                "janela do Overwatch %dx%d não é 16:9 (aspect %.3f); "
                "apenas 16:9 é suportado — resultados podem ser imprecisos",
                width,
                height,
                aspect,
            )
        return {"left": point.x, "top": point.y, "width": width, "height": height}
    except Exception:  # noqa: BLE001 — qualquer falha de Win32 → fallback seguro
        log.debug("falha ao localizar a janela do Overwatch", exc_info=True)
        return None


def grab_screen() -> Image.Image:
    """
    Captura a área do jogo e devolve a imagem RGB em memória.

    Prioriza a JANELA do Overwatch (retângulo do cliente) — suporta multi-monitor
    e modo janela. Se a janela não for encontrada, cai para o MONITOR PRIMÁRIO
    (comportamento histórico), sem travar.
    """
    with mss.mss() as sct:
        client = find_overwatch_client_rect()
        if client is not None:
            monitor = client
            source = "janela do Overwatch"
        else:
            monitor_index = 1 if len(sct.monitors) > 1 else 0
            monitor = sct.monitors[monitor_index]
            source = f"monitor primário ({monitor_index})"
        sct_img = sct.grab(monitor)
        full_img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
    log.debug("captura: %s, resolução %dx%d", source, *full_img.size)
    return full_img


def crop_capture(
    full_img: Image.Image, role: str | None, layout: dict | None = None
) -> CaptureResult:
    """Recorta retratos (4 variações de perk) e slots de ban EM MEMÓRIA.

    A geometria vem do layout versionado (data/layouts/ow_hero_select.json);
    `layout` pode ser injetado nos testes. A escala é linear a partir da
    resolução-base do layout (mesma matemática da região do mapa).
    """
    if layout is None:
        layout = datasource.load_layout()

    base = layout.get("base_resolution", {})
    base_w = base.get("width", _FALLBACK_BASE[0])
    base_h = base.get("height", _FALLBACK_BASE[1])

    full_w, full_h = full_img.size
    scale_x = full_w / base_w
    scale_y = full_h / base_h
    skip_files = _skip_files_for_role(role)

    lineup = layout.get("lineup", {})
    buffer = lineup.get("vertical_buffer", 0)
    portrait = lineup.get("portrait", {})
    p_w = portrait.get("width", 44)
    p_h = portrait.get("height", 44)
    slots = lineup.get("slots", [])
    perks = lineup.get("perks", [])

    portraits: dict[str, dict[str, Image.Image]] = {}
    for perk in perks:
        perk_name = perk["name"]
        left_base = perk["left"]
        crops: dict[str, Image.Image] = {}
        for c in slots:
            if c["name"] in skip_files:
                continue
            # Área maior (buffer vertical) para a busca da janela deslizante.
            top_with_buffer = c["top"] - buffer
            height_with_buffer = p_h + (2 * buffer)
            box = resolution.scale_and_clamp(
                left_base,
                top_with_buffer,
                p_w,
                height_with_buffer,
                scale_x,
                scale_y,
                full_w,
                full_h,
            )
            crops[c["name"]] = full_img.crop(box)
        portraits[perk_name] = crops

    # Bans: recorte EXATO (sem buffer) — slot fixo na UI, matching direto.
    bans: dict[str, Image.Image] = {}
    for b in layout.get("bans", {}).get("slots", []):
        box = resolution.scale_and_clamp(
            b["left"], b["top"], b["width"], b["height"], scale_x, scale_y, full_w, full_h
        )
        bans[b["name"]] = full_img.crop(box)

    return CaptureResult(full=full_img, resolution=(full_w, full_h), portraits=portraits, bans=bans)


def capture() -> CaptureResult:
    """Captura a tela e devolve todos os recortes em memória (sem I/O de disco)."""
    role = storage.read_role()
    if role is None:
        print("Role não encontrada. Escolha a sua Função")
    return crop_capture(grab_screen(), role)


def save_debug_artifacts(cap: CaptureResult, outdir: str | None = None) -> None:
    """Grava os PNGs intermediários (apenas debug; era o comportamento padrão)."""
    if outdir is None:
        outdir = debug_dir()
    os.makedirs(outdir, exist_ok=True)
    cap.full.save(os.path.join(outdir, "full.png"))
    for perk_name, crops in cap.portraits.items():
        perk_dir = os.path.join(outdir, perk_name)
        os.makedirs(perk_dir, exist_ok=True)
        for name, img in crops.items():
            img.save(os.path.join(perk_dir, name))
    bans_dir = os.path.join(outdir, "bans")
    os.makedirs(bans_dir, exist_ok=True)
    for name, img in cap.bans.items():
        img.save(os.path.join(bans_dir, name))
    log.debug("artefatos de debug gravados em %s", os.path.abspath(outdir))


def executar() -> CaptureResult:
    """Compatibilidade CLI: captura e TAMBÉM grava os artefatos em print/."""
    cap = capture()
    save_debug_artifacts(cap)
    return cap


if __name__ == "__main__":
    executar()
