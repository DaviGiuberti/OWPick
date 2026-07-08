"""
coletar_stats2.py  –  v1.0
==========================
Scraper ALTERNATIVO de winrate/pickrate por mapa, coletado direto do site
OFICIAL da Blizzard (não do owtics.gg usado por `coletar_stats.py`):

  https://overwatch.blizzard.com/en-us/rates/?input=PC&map=<slug>&region=<região>&role=All&rq=1&tier=<tier>

Usa-se o locale `en-us` (e não `pt-br`) DE PROPÓSITO: no site PT-BR alguns nomes
são localizados ("Soldado: 76", "Rainha Junker"), o que quebraria o casamento com
os nomes canônicos (em inglês) do projeto. O locale só afeta os RÓTULOS; os
números de winrate/pickrate são os mesmos.

Gera EXATAMENTE o mesmo `stats_inputs.csv` consumido pelo projeto — colunas
idênticas às de `coletar_stats.py` — e roda de forma completamente independente
dele (nenhum import entre os dois).

Como a extração funciona
------------------------
A página da Blizzard já traz TODOS os dados embutidos no HTML entregue pelo
servidor (Server-Side Rendering). Não é preciso Playwright/navegador: um simples
GET com `urllib` basta. Os dados vêm como JSON *HTML-escapado* dentro do markup,
uma entrada por herói, no formato (após des-escapar as entidades HTML):

    "cells":{"name":"Jetpack Cat","winrate":63.3,"pickrate":5.6,"banrate":10.4}

Cada entrada aparece DUAS vezes na página (SSR + hidratação do cliente); a
des-duplicação é feita por nome (os valores são idênticos). O projeto usa apenas
`winrate` e `pickrate` — `banrate` é ignorado.

Estratégia (robusta a pequenas mudanças de layout):
  1. Baixa o HTML da página (GET com User-Agent de navegador).
  2. Des-escapa as entidades HTML (`&quot;` -> `"`), obtendo JSON legível.
  3. Extrai cada bloco `"cells":{...}` por regex e faz `json.loads` do objeto.
  4. Se NENHUM bloco for encontrado numa página que respondeu 200, o layout
     provavelmente mudou -> a página é reportada como sem dados (aviso claro),
     sem derrubar a coleta dos demais mapas.

Instalação
----------
Nenhuma dependência externa além do que o projeto já usa (só a stdlib para o
download). Uso:

  python tools/coletar_stats2.py [destino.csv] [região] [tier]

  - destino.csv : opcional; padrão data/stats_inputs.csv do repositório.
  - região      : opcional; padrão "Americas" (Blizzard). Aceita também os
                  códigos do settings do app ("AMER" etc.) via REGION_ALIASES.
  - tier        : opcional; padrão "Grandmaster". Aceita também os valores do
                  settings ("GRANDMASTER_AND_CHAMPION" etc.) via TIER_ALIASES.
"""

from __future__ import annotations

import csv
import html
import json
import logging
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Ferramenta externa: os módulos do app vivem no pacote owpick (src/).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from owpick.core import heroes  # noqa: E402 — fonte única de heróis e mapas

# ─────────────────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Configuração
# ─────────────────────────────────────────────────────────────────────────────
PATCH = "Season 3 · 2026 (Reign of Talon: Into the Tiger's Den)"
BASE_URL = "https://overwatch.blizzard.com/en-us/rates/"
DELAY_MIN = 1.5
DELAY_MAX = 3.0
TIMEOUT = 40  # segundos por request

# Região/tier no formato esperado pela Blizzard. Podem ser sobrescritos por
# argv[2]/argv[3]. Os ALIASES traduzem os códigos usados pelo settings do app
# (compartilhados com o scraper antigo) para os rótulos da Blizzard, de modo que
# o app possa passar os mesmos valores de settings.json sem adaptação.
DEFAULT_REGION = "Americas"
DEFAULT_TIER = "Grandmaster"

REGION_ALIASES = {
    "AMER": "Americas",
    "AMERICAS": "Americas",
    "EU": "Europe",
    "EUROPE": "Europe",
    "ASIA": "Asia",
}
TIER_ALIASES = {
    "GRANDMASTER_AND_CHAMPION": "Grandmaster",
    "GRANDMASTER": "Grandmaster",
    "MASTER": "Master",
    "DIAMOND": "Diamond",
    "PLATINUM": "Platinum",
    "GOLD": "Gold",
    "SILVER": "Silver",
    "BRONZE": "Bronze",
    "ALL": "All",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Regex do bloco de dados de cada herói, aplicado sobre o HTML JÁ DES-ESCAPADO.
# Ex.: "cells":{"name":"D.Va","winrate":57.8,"pickrate":12.4,"banrate":3.1}
# O nome é capturado de forma preguiçosa até a próxima chave para tolerar nomes
# com pontuação ("D.Va", "Soldier: 76", "Wrecking Ball", "Lúcio").
_CELL_RE = re.compile(
    r'"cells":\{"name":"(?P<name>.*?)",'
    r'"winrate":(?P<winrate>[0-9.]+),'
    r'"pickrate":(?P<pickrate>[0-9.]+)'
)

# ─────────────────────────────────────────────────────────────────────────────
#  Heróis e mapas — fonte única: owpick.core.heroes
# ─────────────────────────────────────────────────────────────────────────────
# Mapas competitivos (nome, slug, modo). O slug do projeto já bate com o slug
# usado pela Blizzard (ex.: "watchpoint-gibraltar", "kings-row", "paraiso").
MAPS: list[tuple[str, str, str]] = heroes.MAPS_DATA

# Função canônica de normalização de nomes (fonte única).
slugify = heroes.normalize_hero_name

CSV_FIELDS = ["map", "map_type", "map_slug", "hero", "role", "winrate", "pickrate"]

# ─────────────────────────────────────────────────────────────────────────────
#  Utilitários
# ─────────────────────────────────────────────────────────────────────────────


def load_heroes() -> dict:
    """Heróis a partir do core (fonte única)."""
    return {"version": "1.0.0", "patch": PATCH, "heroes": heroes.load_heroes_roles()}


def hero_role_map(data: dict) -> dict[str, str]:
    return {h: role for role, hero_list in data["heroes"].items() for h in hero_list}


def all_heroes_list(data: dict) -> list[str]:
    return [h for hero_list in data["heroes"].values() for h in hero_list]


def safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
        return float(value)
    except (ValueError, TypeError):
        return None


def fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else ""


def build_url(slug: str, region: str, tier: str) -> str:
    """Monta a URL da página de rates da Blizzard para um mapa."""
    return (
        f"{BASE_URL}?input=PC&map={slug}&region={region}"
        f"&role=All&rq=1&tier={tier}"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Download + extração
# ─────────────────────────────────────────────────────────────────────────────


def fetch_html(url: str) -> str | None:
    """GET simples com User-Agent de navegador. `None` em caso de erro de rede."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        log.warning(f"  erro ao carregar {url} – {e}")
        return None


def parse_stats(page_html: str) -> dict[str, dict]:
    """Extrai {nome_da_blizzard: {winrate, pickrate}} do HTML da página.

    Des-escapa as entidades HTML e casa cada bloco `"cells":{...}`. Cada entrada
    aparece duplicada na página (SSR + hidratação) — a des-duplicação é natural,
    pois usamos um dict por nome (valores idênticos). Retorna {} se o layout não
    for reconhecido (nenhum bloco encontrado).
    """
    unescaped = html.unescape(page_html)
    result: dict[str, dict] = {}
    for m in _CELL_RE.finditer(unescaped):
        name = m.group("name").strip()
        if not name or len(name) < 2:
            continue
        result[name] = {
            "winrate": safe_float(m.group("winrate")),
            "pickrate": safe_float(m.group("pickrate")),
        }
    return result


def scrape_map(slug: str, name: str, region: str, tier: str) -> dict[str, dict]:
    """Retorna {hero_name: {winrate, pickrate}} ou {} se o mapa não tiver dados."""
    url = build_url(slug, region, tier)
    log.info(f"  GET {url}")

    page_html = fetch_html(url)
    if page_html is None:
        return {}

    data = parse_stats(page_html)
    if not data:
        # Página respondeu mas nenhum bloco foi reconhecido: layout mudou ou o
        # mapa/tier não tem dados. Aviso claro; a coleta segue para os demais.
        log.warning(
            f"  {name}: nenhum dado extraído (layout mudou ou mapa/tier sem dados)."
        )
        return {}

    log.info(f"  {name}: {len(data)} heróis (HTML Blizzard).")
    return data


def match_hero(hero: str, data: dict[str, dict]) -> dict | None:
    """Casa o nome canônico do projeto com o nome vindo da Blizzard (por slug)."""
    if hero in data:
        return data[hero]
    target = slugify(hero)
    for key, val in data.items():
        if slugify(key) == target:
            return val
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Pipeline principal
# ─────────────────────────────────────────────────────────────────────────────


def resolve_region(raw: str) -> str:
    """Traduz o código do settings/app para o rótulo da Blizzard (ou usa cru)."""
    return REGION_ALIASES.get(raw.strip().upper(), raw.strip() or DEFAULT_REGION)


def resolve_tier(raw: str) -> str:
    return TIER_ALIASES.get(raw.strip().upper(), raw.strip() or DEFAULT_TIER)


def run() -> None:
    region = resolve_region(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_REGION
    tier = resolve_tier(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_TIER

    heroes_data = load_heroes()
    role_map = hero_role_map(heroes_data)
    all_heroes = all_heroes_list(heroes_data)

    log.info("=" * 62)
    log.info("Blizzard Rates Scraper v1.0 (coletar_stats2)")
    log.info(f"Patch  : {heroes_data.get('patch', '?')}")
    log.info(f"Heróis : {len(all_heroes)}")
    log.info(f"Mapas  : {len(MAPS)}")
    log.info(f"Região : {region}  |  Tier: {tier}")
    log.info(f"Linhas CSV esperadas: {len(all_heroes) * len(MAPS)}")
    log.info("=" * 62)

    records: list[dict] = []

    for map_name, map_slug, map_type in MAPS:
        log.info(f"\n[{map_type}] {map_name}")
        map_data = scrape_map(map_slug, map_name, region, tier)

        for hero in all_heroes:
            stats = match_hero(hero, map_data)
            wr_raw = stats["winrate"] if stats else None
            pr_raw = stats["pickrate"] if stats else None
            records.append(
                {
                    "map": map_name,
                    "map_type": map_type,
                    "map_slug": map_slug,
                    "hero": hero,
                    "role": role_map.get(hero, "UNKNOWN"),
                    "winrate": fmt(safe_float(wr_raw)),
                    "pickrate": fmt(safe_float(pr_raw)),
                }
            )

        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        log.info(f"  Pausando {delay:.1f}s…")
        time.sleep(delay)

    # ── Grava CSV ─────────────────────────────────────────────────
    # Destino: argv[1] se fornecido (o app passa o override do usuário em
    # %APPDATA%\OWPick); senão data/ do repositório (uso dev).
    out_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else _REPO_ROOT / "data" / "stats_inputs.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    # ── Resumo ────────────────────────────────────────────────────
    total = len(records)
    filled = sum(1 for r in records if r["winrate"] != "")
    missing = total - filled

    log.info("\n" + "=" * 62)
    log.info(f"CSV salvo : {out_csv}")
    log.info(f"  Total de linhas : {total}")
    log.info(f"  Com dados       : {filled}")
    log.info(f"  Sem dados (NaN) : {missing}")
    if missing:
        miss_heroes = sorted({r["hero"] for r in records if r["winrate"] == ""})
        miss_maps = sorted({r["map"] for r in records if r["winrate"] == ""})
        log.info(f"  Heróis sem dados : {', '.join(miss_heroes)}")
        log.info(f"  Mapas sem dados  : {', '.join(miss_maps)}")
    log.info("=" * 62)
    log.info("Concluído!")


if __name__ == "__main__":
    run()
