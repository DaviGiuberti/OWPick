"""
utils.py — Fonte de dados e utilitários compartilhados do OWPick.

Este módulo é a ÚNICA fonte de dados de heróis e mapas do programa:
  - A lista de heróis por role está embutida em HEROES_ROLES (não lê mais
    heroes_roles.json em runtime).
  - A lista de mapas está embutida em MAPS_DATA (não lê mais maps.txt em
    runtime).

Também centraliza:
  - resource_path()            (antes duplicada em vários módulos)
  - leitura/cache das planilhas (carregadas uma única vez)
  - normalização de nomes de herói (compatibiliza "D.Va"/"DVa" e
    "Soldier: 76"/"Soldier 76")
  - a matemática de resolução (720p / 1080p / 2K e quaisquer outras), por
    escala/interpolação, sem tabelas independentes por resolução.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
def resource_path(relative_path: str) -> str:
    """
    Caminho absoluto para um recurso somente-leitura, funcionando tanto em
    execução normal (.py) quanto empacotado em .exe (PyInstaller).
    """
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


# ---------------------------------------------------------------------------
# Fonte canônica de HERÓIS (embutida — não lê heroes_roles.json)
# ---------------------------------------------------------------------------
HEROES_ROLES: Dict[str, List[str]] = {
    "DPS": [
        "Anran", "Ashe", "Bastion", "Cassidy", "Echo", "Emre", "Freja",
        "Genji", "Hanzo", "Junkrat", "Mei", "Pharah", "Reaper", "Shion",
        "Sierra", "Sojourn", "Soldier: 76", "Sombra", "Symmetra", "Torbjörn",
        "Tracer", "Vendetta", "Venture", "Widowmaker",
    ],
    "TANK": [
        "D.Va", "Domina", "Doomfist", "Hazard", "Junker Queen", "Mauga",
        "Orisa", "Ramattra", "Reinhardt", "Roadhog", "Sigma", "Winston",
        "Wrecking Ball", "Zarya",
    ],
    "SUP": [
        "Ana", "Baptiste", "Brigitte", "Illari", "Jetpack Cat", "Juno",
        "Kiriko", "Lifeweaver", "Lúcio", "Mercy", "Mizuki", "Moira",
        "Wuyang", "Zenyatta",
    ],
}

# Slots por time em cada role — usado para a pickrate neutra (pr_neutra).
SLOTS: Dict[str, int] = {"DPS": 2, "TANK": 1, "SUP": 2}


def load_heroes_roles() -> Dict[str, List[str]]:
    """Retorna {role: [heróis]} a partir da constante embutida."""
    return HEROES_ROLES


def get_all_heroes() -> List[str]:
    """Lista achatada de todos os heróis, independente da role."""
    return [h for heroes in HEROES_ROLES.values() for h in heroes]


def get_hero_role(hero_name: str) -> Optional[str]:
    """Retorna a role (DPS/TANK/SUP) de um herói, ou None se não encontrado."""
    target = normalize_hero_name(hero_name)
    for role, heroes in HEROES_ROLES.items():
        for h in heroes:
            if normalize_hero_name(h) == target:
                return role
    return None


def get_role_neutral_pickrates() -> Dict[str, float]:
    """{role: pr_neutra}, pr_neutra = slots_por_time / |heróis(role)| (fração)."""
    return {
        role: SLOTS[role] / len(heroes)
        for role, heroes in HEROES_ROLES.items()
        if heroes and role in SLOTS
    }


# ---------------------------------------------------------------------------
# Fonte canônica de MAPAS (embutida — não lê maps.txt)
#   (nome, slug, modo) — slug/modo usados pelo scraper coletar_stats.py
# ---------------------------------------------------------------------------
MAPS_DATA: List[Tuple[str, str, str]] = [
    # CONTROL
    ("Antarctic Peninsula", "antarctic-peninsula", "Control"),
    ("Busan",               "busan",               "Control"),
    ("Ilios",               "ilios",               "Control"),
    ("Lijiang Tower",       "lijiang-tower",       "Control"),
    ("Nepal",               "nepal",               "Control"),
    ("Oasis",               "oasis",               "Control"),
    ("Samoa",               "samoa",               "Control"),
    # ESCORT
    ("Circuit Royal",         "circuit-royal",        "Escort"),
    ("Dorado",                "dorado",               "Escort"),
    ("Havana",                "havana",               "Escort"),
    ("Junkertown",            "junkertown",           "Escort"),
    ("Rialto",                "rialto",               "Escort"),
    ("Route 66",              "route-66",             "Escort"),
    ("Shambali Monastery",    "shambali-monastery",   "Escort"),
    ("Watchpoint: Gibraltar", "watchpoint-gibraltar", "Escort"),
    # HYBRID
    ("Blizzard World", "blizzard-world", "Hybrid"),
    ("Eichenwalde",    "eichenwalde",    "Hybrid"),
    ("Hollywood",      "hollywood",      "Hybrid"),
    ("King's Row",     "kings-row",      "Hybrid"),
    ("Midtown",        "midtown",        "Hybrid"),
    ("Numbani",        "numbani",        "Hybrid"),
    ("Paraíso",        "paraiso",        "Hybrid"),
    # PUSH
    ("Colosseo",         "colosseo",         "Push"),
    ("Esperança",        "esperanca",        "Push"),
    ("New Queen Street", "new-queen-street", "Push"),
    ("Runasapi",         "runasapi",         "Push"),
    # FLASHPOINT
    ("New Junk City", "new-junk-city", "Flashpoint"),
    ("Suravasa",      "suravasa",      "Flashpoint"),
    # RECENTE
    ("Neon Junction", "neon-junction", "Hybrid"),
]


def get_map_names() -> List[str]:
    """Lista de nomes de mapas (para fuzzy match do OCR em map.py)."""
    return [name for name, _slug, _mode in MAPS_DATA]


# ---------------------------------------------------------------------------
# Normalização de nomes de heróis
# ---------------------------------------------------------------------------
def normalize_hero_name(name: str) -> str:
    """
    Normaliza um nome para uma chave estável e tolerante a variações de
    pontuação/acentuação/capitalização:

      "D.Va" / "DVa"            -> "dva"
      "Soldier: 76" / "Soldier 76" -> "soldier-76"
      "Lúcio" -> "lucio"        "Torbjörn" -> "torbjorn"

    Remove `: . ' \\`` antes de normalizar, depois remove acentos, força
    minúsculas e troca não-alfanuméricos por '-'. Garante que todas as
    variações de um mesmo herói mapeiem para a mesma chave.
    """
    if name is None:
        return ""
    s = re.sub(r"[:\.\'\`]", "", str(name))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def build_matrix_dict(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    Converte uma planilha (DataFrame indexado por herói) em um dicionário
    aninhado com chaves normalizadas: { norm(linha): { norm(coluna): valor } }.
    """
    result: Dict[str, Dict[str, float]] = {}
    for row_hero, row in df.iterrows():
        inner: Dict[str, float] = {}
        for col_hero, value in row.items():
            if pd.notna(value):
                try:
                    inner[normalize_hero_name(col_hero)] = float(value)
                except (TypeError, ValueError):
                    continue
        result[normalize_hero_name(row_hero)] = inner
    return result


# ---------------------------------------------------------------------------
# Leitura/cache das planilhas (carregadas UMA única vez por execução)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def read_heroes_ally_data(filepath: str = "heroes ally.xlsx") -> pd.DataFrame:
    """Planilha de sinergias (cacheada)."""
    return pd.read_excel(resource_path(filepath), sheet_name=0, index_col=0)


@lru_cache(maxsize=1)
def read_heroes_enemy_data(filepath: str = "heroes enemy.xlsx") -> pd.DataFrame:
    """Planilha de counters (cacheada)."""
    return pd.read_excel(resource_path(filepath), sheet_name=0, index_col=0)


@lru_cache(maxsize=1)
def get_ally_matrix() -> Dict[str, Dict[str, float]]:
    """Matriz de sinergias normalizada (cacheada)."""
    return build_matrix_dict(read_heroes_ally_data())


@lru_cache(maxsize=1)
def get_enemy_matrix() -> Dict[str, Dict[str, float]]:
    """Matriz de counters normalizada (cacheada)."""
    return build_matrix_dict(read_heroes_enemy_data())


@lru_cache(maxsize=1)
def read_stats_inputs(filepath: str = "stats_inputs.csv") -> pd.DataFrame:
    """CSV de winrate/pickrate por mapa (cacheado)."""
    return pd.read_csv(resource_path(filepath))


# ---------------------------------------------------------------------------
# Resolução — matemática centralizada (720p / 1080p / 2K / outras)
# ---------------------------------------------------------------------------
BASE_RESOLUTION = (1280, 720)                # resolução de referência (escala 1.0)
KNOWN_RESOLUTIONS = {                          # pastas de templates disponíveis
    "720p": (1280, 720),
    "2k":   (2560, 1440),
}


def resolution_scale(full_w: int, base: Tuple[int, int] = BASE_RESOLUTION) -> float:
    """Fator de escala linear da largura em relação à resolução base (720p)."""
    return full_w / base[0]


def nearest_resolution_key(full_w: int, full_h: int,
                           resolutions: Optional[Dict[str, Tuple[int, int]]] = None
                           ) -> Optional[str]:
    """
    Chave de resolução conhecida mais próxima da tela atual. Em caso de empate
    (ex.: 1080p é equidistante de 720p e 2K), prefere a MAIOR resolução —
    derivar de uma âncora de maior resolução tende a preservar mais qualidade.
    """
    resolutions = resolutions or KNOWN_RESOLUTIONS
    best_key, best_metric = None, None
    for key, (w, h) in resolutions.items():
        dist = (full_w - w) ** 2 + (full_h - h) ** 2
        metric = (dist, -(w * h))  # empate -> maior área primeiro
        if best_metric is None or metric < best_metric:
            best_metric, best_key = metric, key
    return best_key


# ---------------------------------------------------------------------------
# Escolha do banco de templates pelo TAMANHO do retrato (não pela resolução)
# ---------------------------------------------------------------------------
# Tamanho representativo (px) do retrato de cada banco de templates, medido na
# tela do jogo. É a régua usada para escolher o banco por proximidade de tamanho.
TEMPLATE_BANK_PORTRAIT_PX: Dict[str, float] = {
    "720p": 41.0,   # retrato ~41x41 na tela em 720p (templates ~41px)
    "2k":   82.0,   # retrato ~82x82 na tela em 2K (templates ~82px)
}

# Tamanho-base (px, medido em 720p) do retrato capturado, por tipo de recorte.
# É escalado pela resolução atual antes de escolher o banco (template_bank_for_resolution).
BASE_PORTRAIT_PX = 41.0      # retrato normal (TAB+1 / lineup) em 720p (~41px; em 2K ~82px)
BASE_BAN_PORTRAIT_PX = 31.0  # retrato dos slots de ban do competitivo em 720p (~31px; em 2K ~62px)


def pick_template_bank(portrait_px: float,
                       bank_sizes: Optional[Dict[str, float]] = None) -> str:
    """
    Escolhe o banco de templates cujo retrato representativo é o mais PRÓXIMO em
    tamanho de `portrait_px` (o tamanho, em px, do retrato que será comparado na
    resolução atual). Em caso de empate, prefere o banco de MAIOR resolução
    (mais qualidade), coerente com o desempate de nearest_resolution_key.

    Regra genérica, sem ifs por resolução: o limiar entre dois bancos é o ponto
    médio dos seus tamanhos representativos (≈61.5px para 41/82). Retratos
    menores usam 720p e maiores usam 2k, independentemente da resolução da tela.
    """
    bank_sizes = bank_sizes or TEMPLATE_BANK_PORTRAIT_PX
    best_key, best_metric = None, None
    for key, size in bank_sizes.items():
        metric = (abs(portrait_px - size), -size)  # empate -> maior tamanho (2k)
        if best_metric is None or metric < best_metric:
            best_metric, best_key = metric, key
    return best_key


def template_bank_for_resolution(full_w: int,
                                 base_portrait_px: float = BASE_PORTRAIT_PX) -> str:
    """
    Banco de templates recomendado para a resolução atual (`full_w`), para um
    retrato cujo tamanho em 720p é `base_portrait_px`. Escala o retrato pela
    resolução atual e delega a pick_template_bank.

    Como cada TIPO de retrato (normal vs ban) tem um tamanho-base diferente,
    dois tipos podem cair em bancos diferentes NA MESMA resolução — ex.: em 1080p
    o retrato normal (~61.5px) usa 2k, enquanto o retrato de ban (~46.5px) usa 720p.
    """
    return pick_template_bank(base_portrait_px * resolution_scale(full_w))


# ---------------------------------------------------------------------------
# Configuração de captura (config.json) — região do mapa por resolução
# ---------------------------------------------------------------------------
CONFIG_FILE = "config.json"


@lru_cache(maxsize=1)
def load_capture_config(path: str = CONFIG_FILE) -> dict:
    """Lê config.json (região de captura por resolução). {} em caso de falha."""
    import json
    try:
        with open(resource_path(path), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[utils] AVISO: não foi possível ler {path}: {e}")
        return {}


def _region_to_box(region: dict, scale_x: float, scale_y: float,
                   full_w: int, full_h: int) -> Tuple[int, int, int, int]:
    """Converte {left,top,width,height} (escalado) em caixa (l,t,r,b) clampada."""
    left = int(round(region["left"] * scale_x))
    top = int(round(region["top"] * scale_y))
    w = int(round(region["width"] * scale_x))
    h = int(round(region["height"] * scale_y))
    left = max(0, min(left, full_w - 1))
    top = max(0, min(top, full_h - 1))
    right = max(0, min(left + max(1, w), full_w))
    bottom = max(0, min(top + max(1, h), full_h))
    return (left, top, right, bottom)


def get_scaled_map_region(full_w: int, full_h: int,
                          config: Optional[dict] = None
                          ) -> Optional[Tuple[int, int, int, int]]:
    """
    Caixa de recorte (left, top, right, bottom) da região do nome do mapa para
    QUALQUER resolução, derivada matematicamente das âncoras de config.json
    (sem tabela independente por resolução):

      - resolução igual a uma âncora  -> usa as coordenadas nativas;
      - resolução ENTRE duas âncoras (ex.: 1080p entre 720p e 2K)
          -> interpola linearmente cada coordenada pela fração de largura;
      - resolução FORA do intervalo das âncoras
          -> escala proporcionalmente a partir da âncora mais próxima.

    Centraliza toda a lógica de conversão de resolução da região do mapa.
    """
    config = config if config is not None else load_capture_config()
    if not config:
        return None

    # Âncoras (base_w, entry) ordenadas por largura.
    anchors = []
    for entry in config.values():
        br = entry.get("base_resolution", {})
        if "map_region" in entry and br.get("width"):
            anchors.append((br["width"], br.get("height", full_h), entry["map_region"]))
    if not anchors:
        return None
    anchors.sort(key=lambda a: a[0])

    # Caso 1: dentro do intervalo -> interpola entre as duas âncoras vizinhas.
    for (w0, _h0, r0), (w1, _h1, r1) in zip(anchors, anchors[1:]):
        if w0 <= full_w <= w1 and w1 != w0:
            t = (full_w - w0) / (w1 - w0)
            region = {
                k: r0[k] + t * (r1[k] - r0[k])
                for k in ("left", "top", "width", "height")
            }
            # As coordenadas já estão na escala da resolução atual.
            return _region_to_box(region, 1.0, 1.0, full_w, full_h)

    # Caso 2: fora do intervalo -> escala a partir da âncora mais próxima.
    base_w, base_h, region = min(anchors, key=lambda a: abs(a[0] - full_w))
    return _region_to_box(region, full_w / base_w, full_h / base_h, full_w, full_h)
