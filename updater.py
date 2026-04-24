"""
updater.py  –  Sistema de auto-update do OWPick
------------------------------------------------
Como funciona:
  1. Ao iniciar, baixa 'version.json' do GitHub e compara com a versão local.
  2. Se houver versão nova, pergunta ao usuário se quer atualizar.
  3. O update é baixado (.zip), e um .bat é criado para:
       - Esperar o OWPick.exe fechar
       - Substituir todos os arquivos (OWPick.exe + _internal/)
       - Relançar o programa automaticamente

Como lançar uma atualização (você, desenvolvedor):
  1. Incremente a versão em 'version.txt' antes de buildar (ex: "1.1.0" -> "1.2.0")
  2. Gere o novo executável com PyInstaller normalmente
       (certifique-se de incluir o version.txt no build:
        --add-data "version.txt;." no comando, ou via .spec)
  3. Compacte a pasta dist/OWPick inteira num .zip chamado 'OWPick_v1.2.0.zip'
  4. Suba o .zip em algum lugar acessível (ex: GitHub Releases)
  5. Atualize o 'version.json' no GitHub com a nova versão e a URL do .zip
     Só após esse passo os usuários verão a atualização disponível.
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil
import subprocess
import urllib.request
import urllib.error


# =============================================================================
# CONFIGURAÇÃO  –  Altere apenas estas duas constantes
# =============================================================================

VERSION_JSON_URL = "https://raw.githubusercontent.com/DaviGiuberti/Overwatch-Best-Picks/main/version.json"
VERSION_FILE = "version.txt"

# =============================================================================


def resource_path(relative_path: str) -> str:
    """
    Retorna o caminho absoluto para o arquivo, tanto em execução normal quanto
    quando empacotado em .exe (PyInstaller).

    ATENÇÃO: use esta função apenas para leitura de recursos somente-leitura
    embutidos no pacote (ex: version.txt, ícones, assets).
    Para arquivos que precisam persistir/ser escritos no disco (logs, configs),
    use get_exe_dir() em vez desta função.
    """
    try:
        base_path = sys._MEIPASS  # pasta temp onde o PyInstaller extrai os arquivos
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


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
        with open(path, "r", encoding="utf-8") as f:
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
    try:
        req = urllib.request.Request(
            VERSION_JSON_URL,
            headers={"User-Agent": "OWPick-Updater/1.0"}
        )
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


def _apply_update(download_url: str):
    """
    Baixa o .zip, extrai numa pasta temp e cria um .bat que:
      1. Aguarda o OWPick.exe encerrar
      2. Copia os novos arquivos por cima dos antigos (robocopy)
      3. Limpa temporários
      4. Relança o OWPick.exe
    """
    exe_dir  = get_exe_dir()
    exe_path = sys.executable if getattr(sys, "frozen", False) else ""
    tmp_dir  = tempfile.gettempdir()
    zip_path = os.path.join(tmp_dir, "owpick_update.zip")
    ext_dir  = os.path.join(tmp_dir, "owpick_update_extracted")
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

    # --- 3. Cria .bat para substituição pós-saída ---
    bat_lines = [
        "@echo off",
        "echo [OWPick Updater] Aguardando encerramento do programa...",
        "timeout /t 3 /nobreak >nul",
        "echo [OWPick Updater] Limpando instalacao antiga...",
        f'rmdir /S /Q "{os.path.join(exe_dir, "_internal")}" 2>nul',
        f'del /F /Q "{os.path.join(exe_dir, "OWPick.exe")}" 2>nul',
        "echo [OWPick Updater] Aplicando atualizacao...",
        f'robocopy "{source_dir}" "{exe_dir}" /E /NFL /NDL /NJH /NJS >nul',
        "echo [OWPick Updater] Limpando temporarios...",
        f'rmdir /S /Q "{ext_dir}" 2>nul',
        f'del /F /Q "{zip_path}" 2>nul',
        "echo [OWPick Updater] Atualizacao concluida! Reiniciando...",
        f'start "" "{exe_path}"' if exe_path else "echo (Relancamento manual necessario)",
        'del "%~f0"',
    ]

    try:
        with open(bat_path, "w", encoding="cp1252") as f:
            f.write("\r\n".join(bat_lines))
    except Exception as e:
        print(f"    Erro ao criar script de atualização: {e}")
        return

    # --- 4. Lança o .bat e encerra este processo ---
    print("    Encerrando para aplicar atualização...")
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        close_fds=True
    )
    sys.exit(0)


# =============================================================================
# Ponto de entrada principal  –  chamado pela main.py
# =============================================================================

def check_for_updates():
    """
    Verifica se há atualização disponível e pergunta ao usuário.
    Chame esta função no início do programa, antes do menu principal.
    """
    print(">>> Verificando atualizações...")
    info = _fetch_version_info()

    if info is None:
        print("    Não foi possível verificar atualizações (sem conexão ou URL inválida).")
        return

    remote_version = info.get("version", "0.0.0")
    download_url   = info.get("download_url", "")
    notas          = info.get("notas", "")
    local_version  = get_local_version()

    if _parse_version(remote_version) > _parse_version(local_version):
        print(f"    *** Nova versão disponível: {remote_version}  (você tem: {local_version}) ***")
        if notas:
            print(f"    Novidades: {notas}")
        resposta = input("    Deseja atualizar agora? [s/N] ").strip().lower()
        if resposta == "s":
            _apply_update(download_url)
        else:
            print("    Atualização adiada. Você pode atualizar na próxima vez.")
    else:
        print(f"    OWPick está atualizado (versão {local_version}).")