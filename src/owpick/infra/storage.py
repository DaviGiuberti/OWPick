"""storage.py — Persistência dos arquivos do usuário (camada infra).

Lê/escreve os arquivos gerados em runtime no diretório de trabalho:
Roles.txt, {role}.txt, ALL.txt, lineup.txt, bans.txt, current_map.txt.
As mensagens ao usuário ficam na camada ui — aqui só há I/O.
"""

from __future__ import annotations

import os

from owpick import paths
from owpick.core.heroes import VALID_ROLES
from owpick.log import get_logger

log = get_logger("storage")

# Nomes-base dos arquivos. Os de config/dados do usuário (Roles/ALL/role) vivem
# em %APPDATA%\OWPick (paths.user_file); os artefatos de pipeline standalone
# (lineup/bans/current_map) vivem em %LOCALAPPDATA%\OWPick\cache (paths.cache_file).
ROLE_FILE = "Roles.txt"
FAVORITES_FILE = "ALL.txt"  # arquivo de favoritos (todos os heróis do usuário)
LINEUP_FILE = "lineup.txt"
BANS_FILE = "bans.txt"
CURRENT_MAP_FILE = "current_map.txt"


def role_path() -> str:
    """Caminho absoluto do Roles.txt (dado do usuário)."""
    return paths.user_file(ROLE_FILE)


def favorites_path() -> str:
    """Caminho absoluto do ALL.txt (dado do usuário)."""
    return paths.user_file(FAVORITES_FILE)


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------
def read_role(path: str | None = None) -> str | None:
    """
    Leitura CANÔNICA da role do jogador (Roles.txt, gravado por roles.py).

    Retorna a role em maiúsculas ("ALL"/"DPS"/"SUP"/"TANK") ou None se o
    arquivo não existir, estiver vazio/ilegível ou tiver conteúdo inválido.
    """
    if path is None:
        path = role_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            role = f.read().strip().upper()
    except OSError:
        log.warning("não foi possível ler %s", path, exc_info=True)
        return None
    return role if role in VALID_ROLES else None


def write_role(role: str, path: str | None = None) -> None:
    """Grava a role escolhida (substitui o conteúdo)."""
    if path is None:
        path = role_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(role)


# ---------------------------------------------------------------------------
# Heróis jogáveis / favoritos
# ---------------------------------------------------------------------------
def read_playable_heroes(role: str) -> list[str]:
    """Lê os heróis jogáveis da role a partir de {role}.txt."""
    with open(paths.user_file(f"{role}.txt"), encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_favorites(path: str | None = None) -> list[str]:
    """Carrega a lista de heróis favoritos (ALL.txt). Vazia se ausente/ilegível."""
    if path is None:
        path = favorites_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except (OSError, UnicodeDecodeError):
        # Degradação segura: sem favoritos legíveis o usuário refaz a lista
        # (o arquivo é recriado ao salvar) — mas o erro fica registrado.
        log.warning("não foi possível ler %s", path, exc_info=True)
        return []


def save_heroes_to_files(heroes_list: list[str], role_of) -> None:
    """
    Persiste os favoritos: um arquivo por role (DPS/SUP/TANK.txt) + ALL.txt.
    `role_of(hero)` devolve a role do herói (injetado pela ui/favorites).
    """
    heroes_list = list(dict.fromkeys(heroes_list))  # dedup preservando ordem
    heroes_by_role: dict[str, list[str]] = {"DPS": [], "SUP": [], "TANK": []}
    for hero in heroes_list:
        role = role_of(hero)
        if role in heroes_by_role:
            heroes_by_role[role].append(hero)

    for role, filename in [("DPS", "DPS.txt"), ("SUP", "SUP.txt"), ("TANK", "TANK.txt")]:
        with open(paths.user_file(filename), "w", encoding="utf-8") as f:
            if heroes_by_role[role]:
                f.write("\n".join(heroes_by_role[role]))

    with open(favorites_path(), "w", encoding="utf-8") as f:
        if heroes_list:
            f.write("\n".join(heroes_list))


# ---------------------------------------------------------------------------
# Lineup / bans / mapa (gerados pelo pipeline; lidos pelo scoring standalone)
# ---------------------------------------------------------------------------
def read_lineup(filepath: str | None = None) -> tuple[list[str], list[str]]:
    """Lê lineup.txt: linhas [:4] = aliados; linhas [4:9] = inimigos."""
    if filepath is None:
        filepath = paths.cache_file(LINEUP_FILE)
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    with open(filepath, encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    allies = [a for a in lines[:4] if a]
    enemies = [e for e in lines[4:9] if e]
    return allies, enemies


def write_lineup(names: list[str], filepath: str | None = None) -> None:
    if filepath is None:
        filepath = paths.cache_file(LINEUP_FILE)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("".join(f"{n}\n" for n in names))


def read_bans(filepath: str | None = None) -> list[str]:
    """Lê bans.txt (gerado por matching). Lista vazia se ausente/ilegível."""
    if filepath is None:
        filepath = paths.cache_file(BANS_FILE)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        # Degradação segura: sem bans legíveis = nenhuma exclusão por ban.
        log.warning("não foi possível ler %s; seguindo sem bans", filepath, exc_info=True)
        return []


def write_bans(names: list[str], filepath: str | None = None) -> None:
    if filepath is None:
        filepath = paths.cache_file(BANS_FILE)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("".join(f"{n}\n" for n in names))


def read_current_map(filepath: str | None = None) -> str:
    """Lê current_map.txt (gerado por map_detect). 'UNKNOWN' se ausente/ilegível."""
    if filepath is None:
        filepath = paths.cache_file(CURRENT_MAP_FILE)
    if not os.path.exists(filepath):
        return "UNKNOWN"
    try:
        with open(filepath, encoding="utf-8") as f:
            mapa = f.read().strip()
        return mapa or "UNKNOWN"
    except OSError:
        log.warning("não foi possível ler %s; mapa UNKNOWN", filepath, exc_info=True)
        return "UNKNOWN"


def write_current_map(name: str, filepath: str | None = None) -> None:
    if filepath is None:
        filepath = paths.cache_file(CURRENT_MAP_FILE)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(name)
