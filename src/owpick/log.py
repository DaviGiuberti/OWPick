"""log.py — Logging estruturado do OWPick (stdlib `logging`).

Cross-cutting: usado por todas as camadas. Não imprime por conta própria além
do handler de console (que só aparece após setup_logging).

Dois destinos:
  - Arquivo rotativo em %APPDATA%\\OWPick\\logs\\owpick.log (2 x 1MB), nível
    DEBUG: diagnóstico completo (resolução, banco de templates, scores por
    slot, texto bruto do OCR, tempos por etapa).
  - Console em nível INFO (DEBUG com a flag --debug): o console do usuário
    continua limpo; os módulos logam diagnóstico em DEBUG.

Uso nos módulos:
    from owpick.log import get_logger
    log = get_logger("matching")

setup_logging() é chamado UMA vez pelo ponto de entrada (owpick.__main__).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from owpick import paths

# Flag global do modo debug (--debug): console em DEBUG e preservação de
# artefatos intermediários (PNGs de recorte) garantida.
DEBUG_MODE = False

_ROOT_NAME = "owpick"
_configured = False

# Sem setup_logging (ex.: nos testes) nada é emitido.
logging.getLogger(_ROOT_NAME).addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Logger hierárquico do app: get_logger('matching') -> 'owpick.matching'."""
    return logging.getLogger(f"{_ROOT_NAME}.{name}")


def setup_logging(debug: bool = False) -> None:
    """Configura arquivo rotativo (DEBUG) + console (INFO; DEBUG com --debug)."""
    global _configured, DEBUG_MODE
    if _configured:
        return
    DEBUG_MODE = debug

    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(logging.DEBUG)

    try:
        log_dir = paths.logs_dir()
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "owpick.log"), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        root.addHandler(file_handler)
    except OSError:
        # Sem acesso ao disco de logs -> segue só com console; logging nunca
        # derruba o app.
        pass

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    root.addHandler(console)

    _configured = True
