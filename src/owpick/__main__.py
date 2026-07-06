"""Ponto de entrada do OWPick: `python -m owpick` (ou o entry do PyInstaller).

Faz o bootstrap mínimo (path do pacote + console UTF-8) ANTES de importar os
módulos do app, e delega para owpick.ui.console.main().
"""

import os
import sys

# Garante que a raiz `src/` esteja no path — cobre `python -m owpick`,
# `python src/owpick/__main__.py` e o entry script do PyInstaller.
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Console em UTF-8 com fallback: elimina UnicodeEncodeError em consoles de
# codepage legada (cp1252 etc.) ao imprimir símbolos como ✓, ✗, º.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8", errors="replace")

from owpick.ui.console import main  # noqa: E402 — após o bootstrap de path/encoding

if __name__ == "__main__":
    main()
