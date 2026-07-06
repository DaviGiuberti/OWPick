"""datasource.py — Leitura/cache dos dados do modelo (planilhas, CSV, config).

Camada infra: faz o I/O com pandas/json e devolve estruturas prontas (matrizes
normalizadas via core.heroes.build_matrix_dict, DataFrame de stats, dict de
config). Todas as leituras são cacheadas (uma vez por execução).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

import pandas as pd

from owpick import paths
from owpick.core.heroes import build_matrix_dict
from owpick.infra.resources import resource_path
from owpick.log import get_logger

log = get_logger("datasource")

STATS_FILENAME = "stats_inputs.csv"  # nome-base do override do usuário

# O programa lê APENAS os .csv em runtime (tarefa 5.1). A EDIÇÃO continua nos
# .xlsx; o autor roda tools/xlsx_to_csv.py (offline) para regenerar estes .csv
# antes de cada atualização. Os .xlsx e o script NÃO são empacotados.
SYNERGIES_FILE = "data/synergies.csv"  # matriz de sinergias (ex-heroes ally.xlsx)
COUNTERS_FILE = "data/counters.csv"  # matriz de counters (ex-heroes enemy.xlsx)
STATS_FILE = "data/stats_inputs.csv"
LAYOUT_FILE = "data/layouts/ow_hero_select.json"


@lru_cache(maxsize=1)
def read_synergies_data(filepath: str = SYNERGIES_FILE) -> pd.DataFrame:
    """Matriz de sinergias a partir do CSV (cacheada; index_col=0 = herói da linha)."""
    return pd.read_csv(resource_path(filepath), index_col=0)


@lru_cache(maxsize=1)
def read_counters_data(filepath: str = COUNTERS_FILE) -> pd.DataFrame:
    """Matriz de counters a partir do CSV (cacheada; index_col=0 = herói da linha)."""
    return pd.read_csv(resource_path(filepath), index_col=0)


@lru_cache(maxsize=1)
def get_ally_matrix() -> dict[str, dict[str, float]]:
    """Matriz de sinergias normalizada (cacheada)."""
    return build_matrix_dict(read_synergies_data())


@lru_cache(maxsize=1)
def get_enemy_matrix() -> dict[str, dict[str, float]]:
    """Matriz de counters normalizada (cacheada)."""
    return build_matrix_dict(read_counters_data())


def user_stats_path() -> str:
    """Override do usuário para as stats (%APPDATA%\\OWPick\\stats_inputs.csv)."""
    return paths.user_file(STATS_FILENAME)


def stats_source_path() -> str:
    """
    Caminho efetivo do stats_inputs.csv: prefere o OVERRIDE do usuário (gerado
    pela atualização de stats no app, tarefa 5.3) se existir; senão o embutido no
    bundle. Assim a atualização manual persiste entre updates da aplicação.
    """
    override = user_stats_path()
    if os.path.exists(override):
        return override
    return resource_path(STATS_FILE)


@lru_cache(maxsize=1)
def _read_stats_cached(filepath: str) -> pd.DataFrame:
    return pd.read_csv(filepath)


def read_stats_inputs(filepath: str | None = None) -> pd.DataFrame:
    """CSV de winrate/pickrate por mapa (cacheado). Usa o override do usuário se
    existir (ver stats_source_path)."""
    return _read_stats_cached(filepath or stats_source_path())


def refresh_stats_cache() -> None:
    """Invalida o cache das stats (após uma atualização gravar novo override)."""
    _read_stats_cached.cache_clear()


@lru_cache(maxsize=1)
def load_layout(path: str = LAYOUT_FILE) -> dict:
    """
    Lê o layout de captura versionado (data/layouts/ow_hero_select.json):
    slots do lineup, variações de perk, slots de ban e âncoras da região do
    mapa. {} em caso de falha (o chamador degrada). Cacheado.
    """
    try:
        with open(resource_path(path), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        log.warning("não foi possível ler %s: %s", path, e)
        print(f"[datasource] AVISO: não foi possível ler {path}: {e}")
        return {}


def load_capture_config() -> dict:
    """
    Âncoras da região do mapa por resolução (mesma forma que o antigo
    config.json), extraídas do layout. Consumido por resolution.get_scaled_map_region.
    """
    return load_layout().get("map_region_anchors", {})
