"""paths.py — Localização dos três tipos de dado do OWPick (cross-cutting).

Separa claramente onde cada tipo de arquivo vive, para que o app funcione com
qualquer CWD e para que updates/desinstalação nunca toquem nos dados do usuário:

  1. Aplicação (imutável) — templates, planilhas, config, OCR. Resolvida por
     `infra.resources.resource_path` (sys._MEIPASS / raiz do repo). NÃO é tratada
     aqui.
  2. Config/dados do usuário — Roles.txt, favoritos, logs. Vivem em
     `%APPDATA%\\OWPick\\`. Preservados entre updates e desinstalações.
  3. Temporários/debug — recortes de tela (print/), lineup/bans/current_map dos
     fluxos standalone. Vivem em `%LOCALAPPDATA%\\OWPick\\cache\\`. Descartáveis.

Os diretórios-base são resolvidos a CADA chamada (não no import), lendo as
variáveis de ambiente `APPDATA`/`LOCALAPPDATA`. Isso mantém o módulo testável:
os testes apontam essas variáveis para um diretório temporário e obtêm
isolamento total, sem depender do CWD.

Este módulo depende apenas da stdlib e NÃO importa `owpick.log` (log.py delega a
localização dos logs para cá; a dependência é unidirecional).
"""

from __future__ import annotations

import os
import shutil

APP_DIR_NAME = "OWPick"

# Arquivos de config/dados do usuário candidatos à migração automática (2.6).
# São os únicos que representam escolhas do usuário; o resto é derivável.
USER_DATA_FILES = ("Roles.txt", "ALL.txt", "DPS.txt", "SUP.txt", "TANK.txt")


def _env_base(env_var: str) -> str:
    """Raiz do env var (APPDATA/LOCALAPPDATA) com fallback para o home do usuário."""
    root = os.environ.get(env_var)
    if not root:
        root = os.path.expanduser("~")
    return root


def user_data_dir() -> str:
    """Diretório de config/dados do usuário: %APPDATA%\\OWPick."""
    return os.path.join(_env_base("APPDATA"), APP_DIR_NAME)


def cache_dir() -> str:
    """Diretório de temporários/debug: %LOCALAPPDATA%\\OWPick\\cache."""
    return os.path.join(_env_base("LOCALAPPDATA"), APP_DIR_NAME, "cache")


def logs_dir() -> str:
    """Diretório de logs (dado do usuário): %APPDATA%\\OWPick\\logs."""
    return os.path.join(user_data_dir(), "logs")


def user_file(name: str) -> str:
    """Caminho absoluto de um arquivo de dados do usuário."""
    return os.path.join(user_data_dir(), name)


def cache_file(name: str) -> str:
    """Caminho absoluto de um arquivo/pasta temporário ou de debug."""
    return os.path.join(cache_dir(), name)


def ensure_dirs() -> None:
    """Garante que os diretórios de dados do usuário e de cache existam."""
    for d in (user_data_dir(), logs_dir(), cache_dir()):
        os.makedirs(d, exist_ok=True)


def migrate_legacy_user_data(legacy_dirs: list[str] | None = None) -> list[str]:
    """
    Migração automática (primeira execução): copia dados do usuário de versões
    antigas — que gravavam ao lado do exe / no CWD — para `user_data_dir()`.

    Um arquivo só é copiado se AINDA NÃO existir no destino novo (nunca
    sobrescreve dados já migrados). Devolve a lista de arquivos migrados.

    `legacy_dirs` permite injetar as origens nos testes; por padrão usa o CWD e
    o diretório do executável.
    """
    if legacy_dirs is None:
        legacy_dirs = _default_legacy_dirs()

    ensure_dirs()
    dest_dir = user_data_dir()
    migrated: list[str] = []

    for name in USER_DATA_FILES:
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
            continue  # já migrado/definido no local novo — não tocar
        for src_dir in legacy_dirs:
            src = os.path.join(src_dir, name)
            # Evita "copiar sobre si mesmo" caso o CWD já seja o dir novo.
            if os.path.abspath(src) == os.path.abspath(dest):
                continue
            if os.path.exists(src):
                shutil.copy2(src, dest)
                migrated.append(name)
                break

    return migrated


def _default_legacy_dirs() -> list[str]:
    """Origens legadas padrão: diretório do exe (se frozen) e o CWD."""
    dirs: list[str] = []
    import sys

    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
    dirs.append(os.getcwd())
    # Remove duplicatas preservando ordem.
    return list(dict.fromkeys(os.path.abspath(d) for d in dirs))
