"""resources.py — Localização de recursos e identidade do app no Windows.

Camada infra: resolve caminhos de recursos somente-leitura (.py e .exe) e
registra a identidade do processo na taskbar do Windows.
"""

from __future__ import annotations

import os
import sys

# Raiz do repositório em execução .py (este arquivo vive em src/owpick/infra/).
_DEV_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def resource_path(relative_path: str) -> str:
    """
    Caminho absoluto para um recurso somente-leitura, funcionando tanto em
    execução normal (.py, relativo à raiz do repositório — independente do
    CWD) quanto empacotado em .exe (PyInstaller, relativo a _MEIPASS).

    Os recursos usam o MESMO caminho relativo nos dois modos (ex.:
    "assets/heroes", "data/config.json"): o overwatch.spec espelha a
    estrutura do repositório dentro do bundle.
    """
    base_path = getattr(sys, "_MEIPASS", _DEV_BASE)
    return os.path.join(base_path, relative_path)


# ---------------------------------------------------------------------------
# Identidade do aplicativo no Windows (taskbar / atalhos)
# ---------------------------------------------------------------------------
# AppUserModelID explícito do OWPick. DEVE ser idêntico ao AppUserModelID
# gravado nos atalhos pelo instalador (installer.iss): a barra de tarefas do
# Windows agrupa janelas por esse ID e resolve o ícone a partir do atalho do
# Menu Iniciar com o mesmo ID. Sem ele, no Windows 11 (console hospedado no
# Windows Terminal) a janela herda a identidade do Terminal e exibe o ícone
# genérico de terminal.
APP_USER_MODEL_ID = "DaviGiuberti.OWPick"


def configure_windows_app_identity() -> None:
    """
    Registra a identidade do OWPick na barra de tarefas do Windows.

    1. SetCurrentProcessExplicitAppUserModelID: desacopla a janela da
       identidade do host de console (conhost/Windows Terminal), fazendo a
       taskbar tratá-la como "OWPick" (Win10 e Win11).
    2. WM_SETICON: aplica o ícone embutido no OWPick.exe à janela do console
       (título/Alt-Tab), cobrindo o caso de host conhost clássico.

    Deve ser chamada no início do programa, antes de qualquer saída em tela.
    Silenciosa em caso de falha — identidade visual nunca derruba o app.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

    # O ícone só existe embutido quando empacotado pelo PyInstaller.
    if not getattr(sys, "frozen", False):
        return
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return
        large = ctypes.c_void_p()
        small = ctypes.c_void_p()
        ctypes.windll.shell32.ExtractIconExW(
            sys.executable, 0, ctypes.byref(large), ctypes.byref(small), 1
        )
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
        if small.value:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small.value)
        if large.value:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, large.value)
    except Exception:
        pass
