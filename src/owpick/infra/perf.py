"""perf.py — Ajuste de consumo de recursos e instrumentação de tempo (infra).

O OWPick roda AO LADO do Overwatch, num PC que pode ser fraco. Quem precisa dos
recursos é o jogo: o pipeline do TAB+1 é uma ação manual de ~1-2s, então trocar
um pouco da sua latência por menos contenção de CPU/GPU é sempre um bom negócio.

Este módulo concentra os ajustes de ambiente (I/O com o SO e com o OpenCV — por
isso vive em `infra`, não em `core`) e a instrumentação opcional de tempo:

  - `set_below_normal_priority()` — coloca o processo em BELOW_NORMAL no
    agendador do Windows: quando há disputa por CPU, o jogo ganha.
  - `limit_opencv()` — limita as threads internas do OpenCV e DESLIGA o
    despacho automático para OpenCL (GPU integrada). Sem isso o OpenCV usa
    todos os núcleos e pode mandar operações para a mesma GPU que renderiza o
    jogo, exatamente no instante do TAB+1.
  - `stage()` / `process_rss_mb()` — medição por etapa do pipeline, ligada
    SOMENTE no modo debug (custo zero em uso normal).

Tudo aqui é best-effort: qualquer falha é silenciosa e o app segue normalmente.
"""

from __future__ import annotations

import ctypes
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes

from owpick.log import get_logger

log = get_logger("perf")

# Windows: SetPriorityClass (winbase.h). Abaixo do normal, mas acima de IDLE —
# o pipeline continua respondendo rápido quando a CPU está livre.
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000

# Threads internas do OpenCV. 1 é o padrão do OWPick de propósito: os recortes
# são minúsculos (~42x57 px em 720p, ~84x114 em 2K) e o paralelismo interno do
# OpenCV custa mais em sincronização do que economiza em cálculo nesse tamanho.
# Medido nas fixtures 720p/1080p/2K: 1 thread + OpenCL OFF é IGUAL ou MAIS
# RÁPIDO que o padrão (8 threads + OpenCL ON) e devolve 7 núcleos e a GPU
# integrada para o jogo. Os resultados do matching são idênticos nas duas
# configurações (o cálculo é o mesmo; só muda quem o executa).
DEFAULT_OPENCV_THREADS = 1


# ---------------------------------------------------------------------------
# Win32 (kernel32) — assinaturas EXPLÍCITAS
# ---------------------------------------------------------------------------
# `argtypes`/`restype` não são opcionais aqui: sem eles o ctypes trata o retorno
# de GetCurrentProcess() como C int e o pseudo-handle (-1) chega TRUNCADO em 32
# bits nas APIs que esperam um HANDLE de 64 bits. O efeito é silencioso e
# enganoso — SetPriorityClass falha com ERROR_INVALID_HANDLE e o app segue
# achando que ajustou a prioridade.
def _load_kernel32():
    """kernel32 com as assinaturas usadas aqui. None fora do Windows."""
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # pyright: ignore[reportAttributeAccessIssue]
    except (AttributeError, OSError):  # não-Windows
        return None
    k32.GetCurrentProcess.argtypes = []
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.SetPriorityClass.restype = wintypes.BOOL
    return k32


_KERNEL32 = _load_kernel32()


# ---------------------------------------------------------------------------
# Prioridade do processo
# ---------------------------------------------------------------------------
def set_below_normal_priority() -> bool:
    """Coloca o processo em BELOW_NORMAL_PRIORITY_CLASS. False se não der.

    Efeito: em disputa por CPU o Windows serve o Overwatch antes do OWPick. Não
    limita o OWPick quando há núcleo livre — só define quem cede na disputa.
    """
    if _KERNEL32 is None:
        return False
    try:
        ok = bool(
            _KERNEL32.SetPriorityClass(_KERNEL32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        )
    except Exception:  # noqa: BLE001 — API indisponível/negada
        log.debug("não foi possível ajustar a prioridade do processo", exc_info=True)
        return False
    log.debug("prioridade do processo: %s", "BELOW_NORMAL" if ok else "inalterada")
    return ok


# ---------------------------------------------------------------------------
# OpenCV: threads internas e OpenCL (GPU)
# ---------------------------------------------------------------------------
def limit_opencv(threads: int = DEFAULT_OPENCV_THREADS, disable_opencl: bool = True) -> None:
    """Limita as threads do OpenCV e desliga o OpenCL (T-API/GPU).

    `threads <= 0` deixa o OpenCV decidir (comportamento original da lib).
    O import de `cv2` é tardio: este módulo é chamado no boot e não deve, por si
    só, obrigar o carregamento do OpenCV.
    """
    try:
        import cv2
    except Exception:  # noqa: BLE001 — sem OpenCV não há nada a limitar
        return

    if threads > 0:
        try:
            cv2.setNumThreads(threads)
        except Exception:  # noqa: BLE001
            log.debug("cv2.setNumThreads(%s) falhou", threads, exc_info=True)

    if disable_opencl:
        try:
            # Sem isto o OpenCV pode despachar operações para a GPU integrada —
            # a mesma que renderiza o jogo. O processamento aqui é pequeno e
            # roda tranquilamente em CPU.
            cv2.ocl.setUseOpenCL(False)
        except Exception:  # noqa: BLE001 — build sem OpenCL
            log.debug("cv2.ocl.setUseOpenCL(False) falhou", exc_info=True)


def tune_runtime(low_priority: bool = True, opencv_threads: int | None = None) -> None:
    """Aplica todos os ajustes de consumo no boot (chamado por ui.console.main).

    `opencv_threads=None` usa DEFAULT_OPENCV_THREADS; um inteiro sobrescreve
    (0 ou negativo = deixa o OpenCV decidir). Ambos vêm do settings.json.
    """
    if low_priority:
        set_below_normal_priority()
    limit_opencv(DEFAULT_OPENCV_THREADS if opencv_threads is None else opencv_threads)


# ---------------------------------------------------------------------------
# Instrumentação (SOMENTE modo debug — custo zero em uso normal)
# ---------------------------------------------------------------------------
class _MEMORYCOUNTERS(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS (psapi.h)."""

    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_rss_mb() -> float | None:
    """Memória residente (working set) do processo em MB. None se indisponível.

    Usa só a stdlib (`ctypes` + psapi do próprio Windows) — nenhuma dependência
    nova para uma medição que aparece apenas no log de debug.
    """
    if _KERNEL32 is None:
        return None
    try:
        get_info = _KERNEL32.K32GetProcessMemoryInfo
        get_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_MEMORYCOUNTERS),
            wintypes.DWORD,
        ]
        get_info.restype = wintypes.BOOL
        counters = _MEMORYCOUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not get_info(_KERNEL32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return counters.WorkingSetSize / (1024 * 1024)
    except Exception:  # noqa: BLE001 — API indisponível
        return None


@contextmanager
def stage(name: str, enabled: bool) -> Iterator[None]:
    """Mede o tempo de parede de uma etapa e loga em DEBUG. No-op se `enabled`.

    `enabled` vem de `owpick.log.DEBUG_MODE` (flag --debug / settings.debug),
    lido no momento da chamada: fora do debug nem o relógio é consultado.
    """
    if not enabled:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        log.debug("etapa %-10s %7.0f ms", name, (time.perf_counter() - start) * 1000)
