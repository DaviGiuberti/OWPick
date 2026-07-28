"""heroes.py — Fonte canônica de heróis/mapas e normalização de nomes.

Camada core (zero I/O): apenas constantes embutidas e funções puras. As
planilhas e o CSV são lidos pela camada infra (owpick.infra.datasource), que
usa build_matrix_dict daqui para normalizar.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

# ---------------------------------------------------------------------------
# Fonte canônica de HERÓIS (embutida — não lê heroes_roles.json)
# ---------------------------------------------------------------------------
HEROES_ROLES: dict[str, list[str]] = {
    "DPS": [
        "Anran",
        "Ashe",
        "Bastion",
        "Cassidy",
        "Echo",
        "Emre",
        "Freja",
        "Genji",
        "Hanzo",
        "Junkrat",
        "Mei",
        "Pharah",
        "Reaper",
        "Shion",
        "Sierra",
        "Sojourn",
        "Soldier: 76",
        "Sombra",
        "Symmetra",
        "Torbjörn",
        "Tracer",
        "Vendetta",
        "Venture",
        "Widowmaker",
    ],
    "TANK": [
        "D.Va",
        "Domina",
        "Doomfist",
        "Hazard",
        "Junker Queen",
        "Mauga",
        "Orisa",
        "Ramattra",
        "Reinhardt",
        "Roadhog",
        "Sigma",
        "Winston",
        "Wrecking Ball",
        "Zarya",
    ],
    "SUP": [
        "Ana",
        "Baptiste",
        "Brigitte",
        "Illari",
        "Jetpack Cat",
        "Juno",
        "Kiriko",
        "Lifeweaver",
        "Lúcio",
        "Mercy",
        "Mizuki",
        "Moira",
        "Wuyang",
        "Zenyatta",
    ],
}

# Slots por time em cada role — usado para a pickrate neutra (pr_neutra).
SLOTS: dict[str, int] = {"DPS": 2, "TANK": 1, "SUP": 2}

# Valores válidos gravados em Roles.txt ("ALL" = fila aberta).
VALID_ROLES = frozenset({"ALL", "DPS", "SUP", "TANK"})


def load_heroes_roles() -> dict[str, list[str]]:
    """Retorna {role: [heróis]} a partir da constante embutida."""
    return HEROES_ROLES


def get_all_heroes() -> list[str]:
    """Lista achatada de todos os heróis, independente da role."""
    return [h for heroes in HEROES_ROLES.values() for h in heroes]


def get_hero_role(hero_name: str) -> str | None:
    """Retorna a role (DPS/TANK/SUP) de um herói, ou None se não encontrado."""
    target = normalize_hero_name(hero_name)
    for role, heroes in HEROES_ROLES.items():
        for h in heroes:
            if normalize_hero_name(h) == target:
                return role
    return None


def get_role_neutral_pickrates() -> dict[str, float]:
    """{role: pr_neutra}, pr_neutra = slots_por_time / |heróis(role)| (fração)."""
    return {
        role: SLOTS[role] / len(heroes)
        for role, heroes in HEROES_ROLES.items()
        if heroes and role in SLOTS
    }


# ---------------------------------------------------------------------------
# Fonte canônica de MAPAS (embutida — não lê maps.txt)
#   (nome, slug, modo) — slug/modo usados pelo scraper tools/coletar_stats.py
# ---------------------------------------------------------------------------
MAPS_DATA: list[tuple[str, str, str]] = [
    # CONTROL
    ("Antarctic Peninsula", "antarctic-peninsula", "Control"),
    ("Busan", "busan", "Control"),
    ("Ilios", "ilios", "Control"),
    ("Lijiang Tower", "lijiang-tower", "Control"),
    ("Nepal", "nepal", "Control"),
    ("Oasis", "oasis", "Control"),
    ("Samoa", "samoa", "Control"),
    # ESCORT
    ("Circuit Royal", "circuit-royal", "Escort"),
    ("Dorado", "dorado", "Escort"),
    ("Havana", "havana", "Escort"),
    ("Junkertown", "junkertown", "Escort"),
    ("Rialto", "rialto", "Escort"),
    ("Route 66", "route-66", "Escort"),
    ("Shambali Monastery", "shambali-monastery", "Escort"),
    ("Watchpoint: Gibraltar", "watchpoint-gibraltar", "Escort"),
    # HYBRID
    ("Blizzard World", "blizzard-world", "Hybrid"),
    ("Eichenwalde", "eichenwalde", "Hybrid"),
    ("Hollywood", "hollywood", "Hybrid"),
    ("King's Row", "kings-row", "Hybrid"),
    ("Midtown", "midtown", "Hybrid"),
    ("Numbani", "numbani", "Hybrid"),
    ("Paraíso", "paraiso", "Hybrid"),
    # PUSH
    ("Colosseo", "colosseo", "Push"),
    ("Esperança", "esperanca", "Push"),
    ("New Queen Street", "new-queen-street", "Push"),
    ("Runasapi", "runasapi", "Push"),
    # FLASHPOINT
    ("New Junk City", "new-junk-city", "Flashpoint"),
    ("Suravasa", "suravasa", "Flashpoint"),
    # RECENTE
    ("Neon Junction", "neon-junction", "Hybrid"),
]


def get_map_names() -> list[str]:
    """Lista de nomes de mapas (para fuzzy match do OCR em map_detect.py)."""
    return [name for name, _slug, _mode in MAPS_DATA]


# ---------------------------------------------------------------------------
# Aliases de mapa por idioma do cliente do jogo
# ---------------------------------------------------------------------------
# O OCR lê o nome do mapa NO IDIOMA do cliente do Overwatch. Antes o matching só
# comparava contra os nomes em inglês, então um cliente em PT-BR ("Rota 66",
# "Monastério Shambali", ...) virava UNKNOWN e zerava o MetaStrength (afeta boa
# parte do público BR). Aqui mapeamos ALIASES por idioma de volta ao nome
# CANÔNICO (a chave usada em stats_inputs.csv, sempre em inglês).
#
# Formato: { nome_canônico: { código_idioma: alias_localizado } }. Só precisam
# constar os mapas cujo nome MUDA no idioma (nomes próprios como Busan/Ilios/
# Dorado são idênticos nos dois idiomas).
#
# REGRA (validada nas fixtures 1.4): só inclua aliases ANCORADOS num token
# DISTINTIVO (nome próprio/número — Lijiang, Shambali, "66", Antártica,
# Gibraltar). Aliases só com palavras genéricas ("Nova Cidade do Lixo", "Rua Nova
# da Rainha") casam por acaso com OCR ruidoso e roubam o mapa certo (falso
# positivo) — por isso NÃO entram. Extensível para "es"/"fr"/etc. sem tocar no
# código de matching; verificar cada alias contra o cliente antes de adicionar.
MAP_ALIASES: dict[str, dict[str, str]] = {
    "Route 66": {"pt-BR": "Rota 66"},
    "Shambali Monastery": {"pt-BR": "Monastério de Shambali"},
    "Antarctic Peninsula": {"pt-BR": "Península Antártica"},
    "Watchpoint: Gibraltar": {"pt-BR": "Observatório: Gibraltar"},
    "Lijiang Tower": {"pt-BR": "Torre de Lijiang"},
    "New Junk City": {"pt-BR": "Nova Junk City"},
    "Neon Junction": {"pt-BR": "Junção Neon"},
    "New Queen Street": {"pt-BR": "Nova Queen Street"},
}


def get_map_search_index() -> dict[str, str]:
    """
    Índice { texto_pesquisável: nome_canônico } para o fuzzy match do OCR.

    Inclui SEMPRE o nome canônico (inglês) mapeado a si mesmo, mais todos os
    aliases localizados (todos os idiomas) apontando de volta ao canônico. O
    matching compara o OCR contra TODAS as chaves e devolve o canônico — assim o
    cliente em qualquer idioma conhecido resolve para a chave do stats_inputs.csv
    (detecção automática de idioma: tentamos todos ao mesmo tempo).
    """
    index: dict[str, str] = {name: name for name in get_map_names()}
    for canonical, per_lang in MAP_ALIASES.items():
        for alias in per_lang.values():
            index[alias] = canonical
    return index


# ---------------------------------------------------------------------------
# Normalização de nomes de heróis
# ---------------------------------------------------------------------------
# Pontuação presente nos nomes canônicos que NÃO é informação: some na
# normalização e o OCR também não a produz de forma confiável ("D.Va" é lido
# "DVA"/"DVS", "Soldier: 76" vira "SOLDIER 76"). Fonte única para
# normalize_hero_name e para o fuzzy match do infra.player_hero.
HERO_NAME_PUNCTUATION = re.compile(r"[:.'`]")


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
    s = HERO_NAME_PUNCTUATION.sub("", str(name))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def build_matrix_dict(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """
    Converte uma planilha (DataFrame indexado por herói) em um dicionário
    aninhado com chaves normalizadas: { norm(linha): { norm(coluna): valor } }.
    """
    result: dict[str, dict[str, float]] = {}
    for row_hero, row in df.iterrows():
        inner: dict[str, float] = {}
        for col_hero, value in row.items():
            if pd.notna(value):
                try:
                    inner[normalize_hero_name(str(col_hero))] = float(value)
                except (TypeError, ValueError):
                    continue
        result[normalize_hero_name(str(row_hero))] = inner
    return result
