"""Testes do ajuste de consumo de recursos (infra/perf.py, v1.2.11).

O ponto central: os ajustes são best-effort e NÃO podem mudar comportamento nem
derrubar o app quando a API do SO falha. Os testes cobrem o contrato (o que é
chamado, com quais valores) sem depender do resultado real do Win32.
"""

from __future__ import annotations

import sys

import pytest

from owpick.infra import perf

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="ajustes Win32/OpenCV")


# ---------------------------------------------------------------------------
# Prioridade do processo
# ---------------------------------------------------------------------------
def test_prioridade_below_normal_e_realmente_aplicada():
    """Regressão: sem argtypes explícitos o pseudo-handle chega truncado em 32
    bits e o SetPriorityClass falha SILENCIOSAMENTE (ERROR_INVALID_HANDLE)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k32.GetPriorityClass.restype = wintypes.DWORD
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = k32.GetCurrentProcess()
    original = k32.GetPriorityClass(handle)
    try:
        assert perf.set_below_normal_priority() is True
        assert k32.GetPriorityClass(handle) == perf.BELOW_NORMAL_PRIORITY_CLASS
    finally:
        # Não deixa o processo do pytest rebaixado para os demais testes.
        k32.SetPriorityClass(handle, original)


def test_falha_do_win32_nao_propaga(monkeypatch):
    """API indisponível => False, sem exceção (o boot não pode quebrar)."""
    monkeypatch.setattr(perf, "_KERNEL32", None)
    assert perf.set_below_normal_priority() is False
    assert perf.process_rss_mb() is None


# ---------------------------------------------------------------------------
# OpenCV: threads e OpenCL
# ---------------------------------------------------------------------------
def test_limit_opencv_aplica_threads_e_desliga_opencl():
    import cv2

    original_threads, original_ocl = cv2.getNumThreads(), cv2.ocl.useOpenCL()
    try:
        perf.limit_opencv(threads=perf.DEFAULT_OPENCV_THREADS)
        assert cv2.getNumThreads() == perf.DEFAULT_OPENCV_THREADS
        assert cv2.ocl.useOpenCL() is False
    finally:
        cv2.setNumThreads(original_threads)
        cv2.ocl.setUseOpenCL(original_ocl)


def test_threads_zero_deixa_o_opencv_decidir():
    """`opencv_threads = 0` no settings = comportamento original da lib."""
    import cv2

    original_threads, original_ocl = cv2.getNumThreads(), cv2.ocl.useOpenCL()
    try:
        cv2.setNumThreads(3)
        perf.limit_opencv(threads=0)
        assert cv2.getNumThreads() == 3  # intocado
        assert cv2.ocl.useOpenCL() is False  # o OpenCL continua desligado
    finally:
        cv2.setNumThreads(original_threads)
        cv2.ocl.setUseOpenCL(original_ocl)


def test_tune_runtime_usa_o_default_quando_o_settings_nao_define(monkeypatch):
    chamadas: list[int] = []
    monkeypatch.setattr(perf, "limit_opencv", lambda threads: chamadas.append(threads))
    monkeypatch.setattr(perf, "set_below_normal_priority", lambda: True)

    perf.tune_runtime(low_priority=True, opencv_threads=None)
    perf.tune_runtime(low_priority=True, opencv_threads=4)
    assert chamadas == [perf.DEFAULT_OPENCV_THREADS, 4]


def test_tune_runtime_respeita_low_priority_desligado(monkeypatch):
    chamou: list[bool] = []
    monkeypatch.setattr(perf, "limit_opencv", lambda threads: None)
    monkeypatch.setattr(perf, "set_below_normal_priority", lambda: chamou.append(True))

    perf.tune_runtime(low_priority=False, opencv_threads=None)
    assert chamou == []


# ---------------------------------------------------------------------------
# Instrumentação (só no modo debug)
# ---------------------------------------------------------------------------
def test_stage_desligado_nao_loga(caplog):
    with caplog.at_level("DEBUG", logger="owpick.perf"), perf.stage("captura", enabled=False):
        pass
    assert caplog.records == []


def test_stage_ligado_loga_a_etapa(caplog):
    with caplog.at_level("DEBUG", logger="owpick.perf"), perf.stage("captura", enabled=True):
        pass
    assert any("captura" in r.getMessage() for r in caplog.records)


def test_stage_loga_mesmo_com_excecao(caplog):
    with caplog.at_level("DEBUG", logger="owpick.perf"):
        with pytest.raises(ValueError), perf.stage("matching", enabled=True):
            raise ValueError("falha simulada")
    assert any("matching" in r.getMessage() for r in caplog.records)


def test_process_rss_mb_devolve_valor_plausivel():
    rss = perf.process_rss_mb()
    assert rss is not None and rss > 0
