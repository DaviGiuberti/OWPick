"""
updater.py  –  Sistema de auto-update do OWPick
------------------------------------------------
Como funciona:
  1. No boot, uma THREAD DE FUNDO baixa 'version.json' do GitHub e compara com
     a versão local (start_background_check — o boot não bloqueia).
  2. Havendo versão nova, a UI avisa; o usuário aplica pelo comando 'update'
     ou ao fechar o programa (apply_pending_update).
  3. O update é baixado (.zip) e um .bat aplica com ROLLBACK: renomeia a
     instalação atual para 'OWPick.old', copia a nova e, se a cópia falhar,
     restaura o backup e relança a versão antiga. No sucesso, o app novo apaga
     o backup ao subir (cleanup_old_backup).

Como lançar uma atualização (você, desenvolvedor) — fluxo automatizado:
  1. Rode 'python tools/bump.py X.Y.Z' (atualiza version.txt + CHANGELOG)
  2. Edite as notas no CHANGELOG, faça o commit e crie a tag 'vX.Y.Z'
  3. O push da tag dispara o workflow (.github/workflows/release.yml): builda
     (PyInstaller + Inno), publica a GitHub Release com o .zip + instalador +
     sha256 e COMMITA o version.json atualizado na main — só então os usuários
     veem a atualização disponível.

Distribuição:
  - NOVOS usuários instalam via 'OWPick Installer.exe' (Inno Setup), que
    instala em %LOCALAPPDATA%\\Programs\\OWPick (per-user, sem admin).
  - Usuários EXISTENTES atualizam por este módulo: o .zip é aplicado por
    cima da pasta de instalação (gravável sem admin — por isso o instalador
    é per-user; NÃO mover a instalação para Program Files).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable

from owpick.infra.resources import resource_path

# Nome da pasta de backup criada pelo update seguro (tarefa 7.1). A versão
# atual é renomeada para cá ANTES de aplicar a nova; se algo falhar, o .bat
# restaura a partir daqui. O app novo apaga a pasta ao subir com sucesso.
BACKUP_DIR_NAME = "OWPick.old"

# Estado da checagem de update não bloqueante (tarefa 7.2). Preenchido pela
# thread de fundo quando há versão nova; consumido pela UI (menu/ao fechar).
pending_update: dict | None = None

# =============================================================================
# CONFIGURAÇÃO  –  Altere apenas estas duas constantes
# =============================================================================

VERSION_JSON_URL = "https://raw.githubusercontent.com/DaviGiuberti/OWPick/main/version.json"
VERSION_FILE = "version.txt"

# =============================================================================


def get_exe_dir() -> str:
    """Retorna a pasta onde o OWPick.exe está rodando."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_local_version() -> str:
    """
    Lê a versão embutida no pacote via resource_path (sys._MEIPASS quando frozen).
    Retorna '0.0.0' se o arquivo não for encontrado.
    """
    path = resource_path(VERSION_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def _parse_version(v: str) -> tuple:
    """Converte '1.2.3' em (1, 2, 3) para comparação numérica."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def _fetch_version_info() -> dict | None:
    """
    Baixa o version.json remoto.
    Estrutura esperada:
    {
        "version": "1.2.0",
        "download_url": "https://...OWPick_v1.2.0.zip",
        "notas": "Descrição opcional do que mudou"
    }
    Retorna None em caso de falha de rede.
    """
    from owpick import settings

    # URL efetiva: override do settings.json (avançado) ou a padrão do projeto.
    url = settings.get().updater_url or VERSION_JSON_URL
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OWPick-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        return None
    except Exception:
        return None


def _download_file(url: str, dest_path: str) -> bool:
    """Baixa 'url' para 'dest_path' com barra de progresso simples."""
    try:

        def _reporthook(count, block_size, total_size):
            if total_size > 0:
                percent = min(int(count * block_size * 100 / total_size), 100)
                bar = "#" * (percent // 5)
                print(f"\r    [{bar:<20}] {percent}%", end="", flush=True)

        urllib.request.urlretrieve(url, dest_path, reporthook=_reporthook)
        print()
        return True
    except Exception as e:
        print(f"\n    Erro no download: {e}")
        return False


def cleanup_old_backup():
    """
    Remove o backup 'OWPick.old' deixado pelo update seguro (tarefa 7.1).

    O .bat de update renomeia a versão antiga para essa pasta antes de aplicar
    a nova e a mantém no lugar caso precise reverter. Quando o app novo sobe com
    sucesso, este passo confirma que a atualização deu certo apagando o backup.
    Só age no executável congelado (em dev, get_exe_dir aponta para o código).
    """
    if not getattr(sys, "frozen", False):
        return
    backup = os.path.join(get_exe_dir(), BACKUP_DIR_NAME)
    if os.path.isdir(backup):
        try:
            shutil.rmtree(backup)
        except OSError:
            # Backup preso (arquivo em uso, permissão): não é fatal — a próxima
            # inicialização tenta de novo. Nunca deve derrubar o boot.
            pass


def _apply_update(download_url: str):
    """
    Baixa o .zip, extrai numa pasta temp e cria um .bat que aplica a atualização
    de forma SEGURA, com rollback (tarefa 7.1):
      1. Aguarda o OWPick.exe encerrar
      2. Renomeia a instalação atual para 'OWPick.old' (rename atômico)
      3. Copia os novos arquivos (robocopy)
      4. Se a cópia falhar (ERRORLEVEL do robocopy >= 8), restaura o 'OWPick.old'
         e relança a versão antiga — o usuário nunca fica sem app
      5. Em caso de sucesso, relança o OWPick.exe (o app novo apaga o backup)
    """
    exe_dir = get_exe_dir()
    exe_path = sys.executable if getattr(sys, "frozen", False) else ""
    tmp_dir = tempfile.gettempdir()
    zip_path = os.path.join(tmp_dir, "owpick_update.zip")
    ext_dir = os.path.join(tmp_dir, "owpick_update_extracted")
    bat_path = os.path.join(tmp_dir, "owpick_update.bat")

    # --- 1. Download ---
    print("    Baixando pacote de atualização...")
    if not _download_file(download_url, zip_path):
        print("    Falha no download. Tente novamente mais tarde.")
        return

    # --- 2. Extração ---
    print("    Extraindo arquivos...")
    try:
        if os.path.exists(ext_dir):
            shutil.rmtree(ext_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(ext_dir)
    except Exception as e:
        print(f"    Erro ao extrair: {e}")
        return

    source_dir = os.path.join(ext_dir, "OWPick")
    if not os.path.isdir(source_dir):
        source_dir = ext_dir

    # --- 3. Cria .bat para substituição pós-saída (update seguro c/ rollback) ---
    bat_lines = _build_update_bat(exe_dir, exe_path, source_dir, ext_dir, zip_path)

    try:
        with open(bat_path, "w", encoding="cp1252") as f:
            f.write("\r\n".join(bat_lines))
    except Exception as e:
        print(f"    Erro ao criar script de atualização: {e}")
        return

    # --- 4. Lança o .bat e encerra este processo ---
    print("    Encerrando para aplicar atualização...")
    subprocess.Popen(
        ["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True
    )
    sys.exit(0)


def _build_update_bat(
    exe_dir: str, exe_path: str, source_dir: str, ext_dir: str, zip_path: str
) -> list[str]:
    """
    Monta as linhas do .bat de update seguro com rollback (tarefa 7.1).

    Extraído para ser testável sem baixar/extrair um .zip real. A ordem é:
    backup atômico da versão atual → aplicar a nova → restaurar em caso de
    falha do robocopy (ERRORLEVEL >= 8) → relançar.
    """
    internal_dir = os.path.join(exe_dir, "_internal")
    exe_file = os.path.join(exe_dir, "OWPick.exe")
    backup_dir = os.path.join(exe_dir, BACKUP_DIR_NAME)
    backup_internal = os.path.join(backup_dir, "_internal")
    backup_exe = os.path.join(backup_dir, "OWPick.exe")
    relaunch = f'start "" "{exe_path}"' if exe_path else "echo (Relancamento manual necessario)"

    return [
        "@echo off",
        "echo [OWPick Updater] Aguardando encerramento do programa...",
        "timeout /t 3 /nobreak >nul",
        # 1) Backup atômico: renomeia a versao atual para OWPick.old. 'move' no
        #    mesmo volume é um rename (instantâneo) — ainda temos a versao antiga
        #    íntegra caso a cópia da nova falhe.
        "echo [OWPick Updater] Preparando backup da versao atual...",
        f'rmdir /S /Q "{backup_dir}" 2>nul',
        f'mkdir "{backup_dir}" 2>nul',
        f'move "{internal_dir}" "{backup_internal}" >nul 2>nul',
        f'move "{exe_file}" "{backup_exe}" >nul 2>nul',
        # 2) Aplica a nova versao.
        "echo [OWPick Updater] Aplicando atualizacao...",
        f'robocopy "{source_dir}" "{exe_dir}" /E /NFL /NDL /NJH /NJS >nul',
        # robocopy: exit codes >= 8 indicam falha de copia (0-7 = sucesso).
        # 3) Rollback: em caso de falha, restaura o backup e relança a versao
        #    antiga. O usuario NUNCA fica sem app.
        "if %ERRORLEVEL% GEQ 8 (",
        "  echo [OWPick Updater] ERRO ao copiar - codigo robocopy %ERRORLEVEL%. Revertendo...",
        f'  rmdir /S /Q "{internal_dir}" 2>nul',
        f'  del /F /Q "{exe_file}" 2>nul',
        f'  move "{backup_internal}" "{internal_dir}" >nul 2>nul',
        f'  move "{backup_exe}" "{exe_file}" >nul 2>nul',
        f'  rmdir /S /Q "{backup_dir}" 2>nul',
        "  echo A versao anterior foi restaurada. Se o problema persistir, baixe o OWPick Installer.",
        "  pause",
        f"  {relaunch}",
        '  del "%~f0"',
        "  exit /b 1",
        ")",
        # 4) Sucesso: limpa temporarios e relança. O OWPick.old é apagado pelo
        #    proprio app ao subir (updater.cleanup_old_backup).
        "echo [OWPick Updater] Limpando temporarios...",
        f'rmdir /S /Q "{ext_dir}" 2>nul',
        f'del /F /Q "{zip_path}" 2>nul',
        "echo [OWPick Updater] Atualizacao concluida! Reiniciando...",
        relaunch,
        'del "%~f0"',
    ]


# =============================================================================
# Ponto de entrada principal  –  chamado pela main.py
# =============================================================================


def _evaluate_update() -> dict | None:
    """
    Baixa o version.json remoto e decide se há atualização.

    Retorna um dict `{"version", "download_url", "notas"}` quando a versão
    remota é MAIOR que a local; `None` quando está atualizado ou a rede falhou.
    Núcleo compartilhado pela checagem bloqueante e pela não bloqueante.
    """
    info = _fetch_version_info()
    if info is None:
        return None
    remote_version = info.get("version", "0.0.0")
    if _parse_version(remote_version) <= _parse_version(get_local_version()):
        return None
    return {
        "version": remote_version,
        "download_url": info.get("download_url", ""),
        "notas": info.get("notas", ""),
    }


def check_for_updates(ask: Callable[[str], str] = input):
    """
    Verifica se há atualização disponível e pergunta ao usuário (fluxo
    BLOQUEANTE, mantido para uso via CLI/testes).

    `ask` é a fonte de resposta do usuário (INJETÁVEL para testes; o default
    real é input(), então em produção o comportamento não muda em nada).
    """
    print(">>> Verificando atualizações...")
    if _fetch_version_info() is None:
        print("    Não foi possível verificar atualizações (sem conexão ou URL inválida).")
        return

    update = _evaluate_update()
    local_version = get_local_version()
    if update is None:
        print(f"    OWPick está atualizado (versão {local_version}).")
        return

    print(f"    *** Nova versão disponível: {update['version']}  (você tem: {local_version}) ***")
    if update["notas"]:
        print(f"    Novidades: {update['notas']}")
    resposta = ask("    Deseja atualizar agora? [s/N] ").strip().lower()
    if resposta == "s":
        _apply_update(update["download_url"])
    else:
        print("    Atualização adiada. Você pode atualizar na próxima vez.")


def start_background_check(on_available: Callable[[dict], None] | None = None):
    """
    Checagem de update NÃO BLOQUEANTE no boot (tarefa 7.2).

    Roda `_evaluate_update` numa thread daemon para o boot ser imediato — nada
    de `input()` nem I/O de rede travando a inicialização. Se houver versão
    nova, publica em `pending_update` e chama `on_available(update)` (a UI usa
    isso para avisar sem bloquear). Erros de rede são silenciosos por design.
    """

    def _worker():
        global pending_update
        try:
            update = _evaluate_update()
        except Exception:
            update = None
        if update is not None:
            pending_update = update
            if on_available is not None:
                try:
                    on_available(update)
                except Exception:
                    pass

    thread = threading.Thread(target=_worker, name="owpick-update-check", daemon=True)
    thread.start()
    return thread


def apply_pending_update() -> bool:
    """
    Aplica a atualização detectada pela checagem de fundo (por comando do menu
    ou ao fechar). Retorna False se não houver update pendente.
    """
    if pending_update is None:
        return False
    _apply_update(pending_update["download_url"])
    return True
