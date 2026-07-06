"""sim.py — Modo manual / simulação (camada ui, tarefa 6.7).

Monta um lineup manualmente e executa APENAS o scoring (sem captura de tela):

    sim mapa=Ilios inimigos=Tracer,Winston aliados=Mei,Ana bans=Sombra

- Chaves em PT ou EN (mapa/map, inimigos/enemies, aliados/allies, bans).
- Nomes de herói com fuzzy match (mesmo mecanismo do menu de favoritos);
  nomes irreconhecíveis são avisados e ignorados.
- Mapa com fuzzy match tolerante a ruído/idioma (reuso de
  map_detect.identify_map — aliases PT-BR incluídos); irreconhecível => UNKNOWN.

Serve para depurar o modelo e demonstrar o programa fora do jogo.
"""

from __future__ import annotations

import re

from owpick import pipeline
from owpick.core.heroes import get_all_heroes, normalize_hero_name
from owpick.infra import storage
from owpick.infra.map_detect import identify_map
from owpick.log import get_logger
from owpick.ui import ranking_view
from owpick.ui.favorites import find_best_match

log = get_logger("sim")

# Confiança mínima para aceitar o mapa digitado (escala do token_set_ratio,
# 0-100). Entrada manual é muito mais limpa que OCR, então o limiar é alto.
MAP_MIN_SCORE = 60.0

# Chaves aceitas (PT e EN) -> chave canônica.
KEY_ALIASES = {
    "mapa": "map",
    "map": "map",
    "inimigos": "enemies",
    "enemies": "enemies",
    "aliados": "allies",
    "allies": "allies",
    "bans": "bans",
    "banidos": "bans",
}

USAGE = (
    "Uso: sim mapa=<mapa> inimigos=<h1,h2,...> aliados=<h1,h2,...> [bans=<h1,...>]\n"
    "Ex.: sim mapa=Ilios inimigos=Tracer,Winston aliados=Mei,Ana"
)

# token: chave=valor, onde o valor vai até a próxima "chave=" (permite nomes
# com espaço, ex.: inimigos=Junker Queen,Tracer).
_TOKEN_RE = re.compile(r"(\w+)\s*=\s*(.*?)(?=\s+\w+\s*=|$)", re.DOTALL)


def parse_sim_args(text: str) -> dict[str, list[str]] | None:
    """
    Faz o parse de "mapa=X inimigos=A,B aliados=C" para
    {"map": [X], "enemies": [A, B], "allies": [C], "bans": [...]}.
    None se nenhuma chave reconhecida for encontrada.
    """
    found: dict[str, list[str]] = {}
    for raw_key, raw_value in _TOKEN_RE.findall(text):
        key = KEY_ALIASES.get(raw_key.strip().lower())
        if key is None:
            continue
        values = [v.strip() for v in raw_value.split(",") if v.strip()]
        found[key] = values
    return found or None


def _resolve_heroes(names: list[str], echo=print) -> list[str]:
    """Fuzzy match de cada nome para o nome canônico; desconhecidos avisados."""
    normalized = {normalize_hero_name(h): h for h in get_all_heroes()}
    resolved: list[str] = []
    for name in names:
        match = find_best_match(name, normalized)
        if match is None:
            echo(f"✗ Herói não reconhecido (ignorado): '{name}'")
            continue
        resolved.append(match)
    return resolved


def _resolve_map(values: list[str], echo=print) -> str:
    """Fuzzy match do mapa digitado (aliases por idioma). UNKNOWN se irreconhecível."""
    if not values:
        return "UNKNOWN"
    text = ",".join(values)
    candidate, score = identify_map(text)
    if candidate and score >= MAP_MIN_SCORE:
        return candidate
    echo(
        f"✗ Mapa não reconhecido: '{text}' (melhor: '{candidate}', score {score:.0f}) — usando UNKNOWN"
    )
    return "UNKNOWN"


def executar(args: str, echo=print) -> pipeline.RankingResult | None:
    """
    Executa a simulação: resolve nomes, roda APENAS o scoring (pipeline.rank)
    e renderiza o ranking. Retorna o RankingResult (ou None em erro de uso).
    """
    parsed = parse_sim_args(args)
    if parsed is None:
        echo(USAGE)
        return None

    role = storage.read_role()
    if role is None:
        echo("Não encontrei sua Role. Use a opção 2 do menu para definir a função que você joga.")
        return None
    try:
        playable = storage.read_playable_heroes(role)
    except OSError:
        echo(
            f"Não encontrei seus favoritos ('{role}.txt'). "
            "Use a opção 3 do menu para escolher os heróis que você joga."
        )
        return None

    allies = _resolve_heroes(parsed.get("allies", []), echo)
    enemies = _resolve_heroes(parsed.get("enemies", []), echo)
    banned = _resolve_heroes(parsed.get("bans", []), echo)
    mapa = _resolve_map(parsed.get("map", []), echo)

    echo(
        f"Simulação: mapa={mapa} | aliados={', '.join(allies) or '-'} | "
        f"inimigos={', '.join(enemies) or '-'}" + (f" | bans={', '.join(banned)}" if banned else "")
    )

    result = pipeline.rank(
        role=role, playable=playable, allies=allies, enemies=enemies, banned=banned, mapa=mapa
    )
    ranking_view.render(result)
    return result
