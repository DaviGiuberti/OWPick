"""stats_update.py — Atualização das stats de meta a partir do app.

Baixa o `stats_inputs.csv` mais recente publicado no repositório (GitHub raw) e
grava no OVERRIDE do usuário (%APPDATA%\\OWPick\\stats_inputs.csv, ver
datasource.stats_source_path), que passa a ser lido em runtime — a atualização
persiste entre updates da aplicação.

Só usa a stdlib (urllib) + pandas (já runtime), então funciona no executável
congelado SEM nenhuma dependência externa: o usuário baixa o app e usa a opção
"atualizar stats" direto, sem Playwright, sem código-fonte, sem navegador.

Fluxo de PUBLICAÇÃO (autor/desenvolvedor): rodar o scraper offline
`tools/coletar_stats.py` para regenerar `data/stats_inputs.csv`, commitar na
main. A partir daí todos os usuários baixam essa versão por aqui.
"""

from __future__ import annotations

import io
import os
import urllib.error
import urllib.request
from collections.abc import Callable

import pandas as pd

from owpick.infra import datasource
from owpick.log import get_logger

log = get_logger("stats_update")

Reporter = Callable[[str], None]

# URL do CSV publicado (mesma convenção do updater/version.json). Aponta para o
# arquivo versionado na branch main; o autor o regenera com o scraper e commita.
STATS_CSV_URL = "https://raw.githubusercontent.com/DaviGiuberti/OWPick/main/data/stats_inputs.csv"

# Colunas mínimas esperadas — um CSV sem elas (ex.: página de erro 404 servida
# como texto) é rejeitado antes de sobrescrever o override do usuário.
REQUIRED_COLUMNS = {"map", "hero", "role", "winrate", "pickrate"}

_TIMEOUT_SECONDS = 20


def _stats_url() -> str:
    """URL efetiva: override do settings.json (avançado) ou a padrão do projeto."""
    from owpick import settings

    return settings.get().stats_url or STATS_CSV_URL


def _validate_csv(data: bytes) -> str | None:
    """None se o CSV é válido; senão a razão (evita gravar lixo por cima)."""
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        return f"não é um CSV válido ({e})"
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return f"faltam colunas {sorted(missing)}"
    if df.empty:
        return "não contém linhas de dados"
    return None


def update_stats(report: Reporter = print) -> bool:
    """
    Baixa o stats_inputs.csv publicado e grava no override do usuário.
    Retorna True em sucesso. Nunca lança — reporta o problema com instrução clara.
    """
    url = _stats_url()
    dest = datasource.user_stats_path()
    report("Baixando as stats de meta mais recentes...")
    log.info("baixando stats de %s -> %s", url, dest)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OWPick-Stats/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            data = resp.read()
    except (urllib.error.URLError, TimeoutError):
        # Degradação segura: sem rede o app segue com as stats atuais/embutidas.
        log.warning("falha ao baixar stats", exc_info=True)
        report(
            "Não foi possível baixar as stats (sem conexão ou servidor indisponível). "
            "Verifique sua internet e tente novamente; o app continua com as stats atuais."
        )
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("erro inesperado ao baixar stats", exc_info=True)
        report(f"Erro ao baixar as stats: {e}. Tente novamente mais tarde.")
        return False

    problem = _validate_csv(data)
    if problem:
        log.warning("CSV de stats inválido: %s", problem)
        report(
            f"O arquivo de stats baixado é inválido ({problem}). "
            "As stats NÃO foram alteradas — tente novamente mais tarde."
        )
        return False

    # Grava de forma atômica: escreve num temporário e substitui, para nunca
    # deixar um override pela metade se a escrita falhar.
    tmp = dest + ".download"
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except OSError as e:
        log.warning("falha ao gravar %s", dest, exc_info=True)
        report(f"Não foi possível salvar as stats em disco: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False

    datasource.refresh_stats_cache()  # runtime passa a ler o novo override
    report(f"Stats atualizadas com sucesso e salvas em:\n  {dest}")
    return True
