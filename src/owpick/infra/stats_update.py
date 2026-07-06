"""stats_update.py — Atualização das stats de meta a partir do app (tarefa 5.3).

Roda o scraper offline (tools/coletar_stats.py) e grava o resultado no OVERRIDE
do usuário (%APPDATA%\\OWPick\\stats_inputs.csv, ver datasource.stats_source_path),
que passa a ser lido em runtime — a atualização manual persiste entre updates.

Pré-requisitos (o scraper usa Playwright, que NÃO é dependência de runtime nem é
empacotado): ambiente com o código-fonte (pasta tools/) e `playwright` instalado
(grupo `scraper` do pyproject) + `playwright install chromium`. No executável
congelado esses pré-requisitos não existem — a função avisa claramente e não trava.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from owpick.infra import datasource
from owpick.log import get_logger

log = get_logger("stats_update")

Reporter = Callable[[str], None]


def _scraper_script() -> Path | None:
    """Localiza tools/coletar_stats.py a partir da raiz do repositório (só existe
    em execução por código-fonte; ausente no .exe congelado)."""
    # src/owpick/infra/stats_update.py -> parents[3] = raiz do repositório.
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "tools" / "coletar_stats.py"
    return script if script.exists() else None


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def update_stats(report: Reporter = print) -> bool:
    """
    Executa o scraper e atualiza o stats_inputs.csv local (override do usuário).
    Retorna True em sucesso. Nunca lança — reporta o problema com instrução clara.
    """
    if getattr(sys, "frozen", False):
        report(
            "Atualização de stats indisponível no executável: o scraper (Playwright) "
            "não é empacotado. Rode a partir do código-fonte com o grupo 'scraper'."
        )
        return False

    script = _scraper_script()
    if script is None:
        report("Scraper não encontrado (tools/coletar_stats.py). Requer o código-fonte.")
        return False

    if not _playwright_available():
        report(
            "Playwright não instalado. Instale com:\n"
            "  uv sync --group scraper   (ou: pip install playwright)\n"
            "  playwright install chromium\n"
            "e tente novamente."
        )
        return False

    from owpick import settings

    cfg = settings.get()
    dest = datasource.user_stats_path()
    report("Coletando stats de meta (isso pode levar alguns minutos)...")
    log.info(
        "executando scraper -> %s (region=%s, tier=%s)", dest, cfg.scraper_region, cfg.scraper_tier
    )
    try:
        # argv: destino, região e tier (vindos do settings.json — tarefa 6.1).
        proc = subprocess.run(
            [sys.executable, str(script), dest, cfg.scraper_region, cfg.scraper_tier],
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("falha ao executar o scraper", exc_info=True)
        report(f"Falha ao executar o scraper: {e}")
        return False

    if proc.returncode != 0:
        report(f"O scraper terminou com erro (código {proc.returncode}). Stats não atualizadas.")
        return False

    datasource.refresh_stats_cache()  # runtime passa a ler o novo override
    report(f"Stats atualizadas com sucesso e salvas em:\n  {dest}")
    return True
