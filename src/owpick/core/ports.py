"""ports.py — Protocolos (interfaces estruturais) entre as camadas.

Definem o contrato que a infra implementa e que o pipeline/core consomem, sem
acoplar o core a implementações concretas (mss, pandas, Tesseract). Uso leve,
"onde faz sentido" — sem framework de injeção de dependências.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from owpick.core.models import CaptureResult


class ScreenCapturer(Protocol):
    """Fonte de captura de tela (implementada por infra.capture)."""

    def capture(self) -> CaptureResult: ...


class MetaSource(Protocol):
    """Fonte das estatísticas de meta por mapa (winrate/pickrate)."""

    def read_stats_inputs(self) -> pd.DataFrame: ...


class MatrixSource(Protocol):
    """Fonte das matrizes de counters/sinergias já normalizadas."""

    def get_ally_matrix(self) -> dict[str, dict[str, float]]: ...

    def get_enemy_matrix(self) -> dict[str, dict[str, float]]: ...
