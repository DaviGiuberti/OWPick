"""ranking_view.py — Apresentação do ranking no console (camada ui).

Formata o RankingResult produzido por owpick.pipeline com `rich` (tarefa 6.5):
tabela com cores por role, top-3 destacado, barras de score e painel de
ameaças. É a única camada que imprime o ranking; o cálculo vive em
core/pipeline — aqui é SÓ apresentação.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from owpick import settings
from owpick.core.heroes import get_hero_role, normalize_hero_name
from owpick.core.models import Recommendation
from owpick.core.scoring import NEUTRAL_WEIGHT
from owpick.i18n import t
from owpick.pipeline import RankingResult

# Console compartilhado da ui (o spinner do pipeline usa o mesmo objeto para
# que prints durante o status não quebrem a renderização). width fixo evita
# quebras imprevisíveis quando a saída não é um terminal (testes/redirect).
console = Console(width=100, highlight=False)

# Quantas recomendações do topo ganham explicação (tarefa 6.4).
EXPLAIN_TOP_N = 3

# Cor por role (tabela de ranking e painel de ameaças).
ROLE_STYLES = {"DPS": "red", "TANK": "blue", "SUP": "green"}

_BAR_MAX_CHARS = 12  # largura máxima da barra de score

# Destaque do herói "campeão" da coluna que o preset ativo prioriza. `orange1` é
# a tonalidade de laranja mais chamativa da paleta padrão do rich (256 cores).
HIGHLIGHT_STYLE = "bold orange1"

# Qual coluna do Recommendation cada preset destaca. "equilibrado" não aparece
# aqui de propósito: não tem destaque especial. É SÓ apresentação — a ordem, o
# score e o ranking vêm prontos do pipeline e não são tocados.
PRESET_HIGHLIGHT_FIELD: dict[str, str] = {
    "counter-first": "counter",
    "meta-first": "meta",
    "conforto+": "synergy",
}


def _role_style(role: str | None) -> str:
    return ROLE_STYLES.get(role or "", "white")


def _highlighted_hero(recommendations: list[Recommendation]) -> Recommendation | None:
    """Recomendação com o maior valor na coluna priorizada pelo preset ativo
    (`None` no "equilibrado" / preset sem destaque ou lista vazia)."""
    field_name = PRESET_HIGHLIGHT_FIELD.get(settings.get().weights_preset)
    if not field_name or not recommendations:
        return None
    return max(recommendations, key=lambda r: getattr(r, field_name))


def _score_bar(total: float, max_abs: float) -> Text:
    """Barra proporcional ao score (verde positivo, vermelho negativo)."""
    if max_abs <= 0:
        return Text("")
    length = round(_BAR_MAX_CHARS * abs(total) / max_abs)
    return Text("█" * length, style="green" if total >= 0 else "red")


def print_threat_ranking(enemies: list[str], threat_weights: dict[str, float]) -> None:
    """Painel de ameaças inimigas (maior → menor peso)."""
    if not enemies:
        return
    sorted_enemies = sorted(
        [(e, threat_weights.get(normalize_hero_name(e), NEUTRAL_WEIGHT)) for e in enemies if e],
        key=lambda x: x[1],
        reverse=True,
    )
    lines = Text()
    for i, (name, score) in enumerate(sorted_enemies):
        style = _role_style(get_hero_role(name))
        lines.append(f"{i + 1}º ", style="bold")
        lines.append(f"{name:<18}", style=style)
        lines.append(f" {t('ranking.threat_label')}: {score:.2f}")
        if i < len(sorted_enemies) - 1:
            lines.append("\n")
    console.print(Panel(lines, title=t("ranking.threat_title"), expand=False))


def print_ranking(result: RankingResult) -> None:
    """Tabela de recomendações ordenada por score total (top-3 destacado)."""
    table = Table(title=None, header_style="bold")
    table.add_column("RANK", justify="right")
    table.add_column("HERO")
    table.add_column("MAP META", justify="right")
    table.add_column("COUNTER", justify="right")
    table.add_column("SYNERGY", justify="right")
    table.add_column("TOTAL", justify="right")
    table.add_column("")  # barra de score

    max_abs = max((abs(r.total) for r in result.recommendations), default=0.0)
    highlight = _highlighted_hero(result.recommendations)
    for rank, rec in enumerate(result.recommendations, start=1):
        is_highlight = highlight is not None and rec is highlight
        hero_text = Text(
            rec.hero.name,
            style=HIGHLIGHT_STYLE if is_highlight else _role_style(rec.hero.role),
        )
        row_style = "bold" if rank <= 3 else ""
        table.add_row(
            f"{rank}",
            hero_text,
            f"{rec.meta:.2f}",
            f"{rec.counter:.2f}",
            f"{rec.synergy:.2f}",
            f"{rec.total:.2f}",
            _score_bar(rec.total, max_abs),
            style=row_style,
        )
    console.print(table)


def render(result: RankingResult) -> None:
    """Imprime o relatório completo do ranking (cabeçalho + ameaças + tabela)."""
    console.print(t("ranking.available", heroes=", ".join(result.playable)) + "\n")
    console.print(t("ranking.allies", names=", ".join(result.allies)))
    console.print(t("ranking.enemies", names=", ".join(result.enemies)))
    if result.banned:
        console.print(t("ranking.banned", names=", ".join(result.banned)))
    console.print(t("ranking.map", map=result.mapa) + "\n")

    if not result.meta_available:
        console.print(f"[yellow]{t('ranking.meta_unavailable')}[/]\n")

    print_threat_ranking(result.enemies, result.threat_weights)

    if result.excluded_ally:
        console.print(t("ranking.excluded_ally", names=", ".join(result.excluded_ally)) + "\n")
    if result.excluded_ban:
        console.print(t("ranking.excluded_ban", names=", ".join(result.excluded_ban)) + "\n")

    if not result.recommendations:
        console.print(t("ranking.empty"))
        return

    print_ranking(result)

    # Explicabilidade (tarefa 6.4): o "por quê" dos top-N, se habilitada no
    # settings (menu do console liga/desliga; persistido em settings.json).
    if settings.get().explain_ranking:
        print_explanations(result)


def print_explanations(result: RankingResult) -> None:
    """Decomposição dos termos dos top-N: qual inimigo pesou, qual sinergia
    puxou, quanto o mapa influenciou."""
    top = result.recommendations[:EXPLAIN_TOP_N]
    if not top:
        return
    console.print(f"\n[bold]{t('ranking.why_title', n=len(top))}[/]")
    for rec in top:
        name = Text(f"  {rec.hero.name}: ", style=f"bold {_role_style(rec.hero.role)}")
        if rec.reasons:
            console.print(name.append("; ".join(rec.reasons), style="not bold default"))
        else:
            console.print(name.append(t("ranking.why_neutral"), style="not bold default"))
    console.print("-" * 36)
