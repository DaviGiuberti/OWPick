"""
owtics_scraper.py  –  v3.0
===========================
Extrai winrate e pickrate de cada personagem por mapa em:
  https://owtics.gg/en-US/map/<slug>?region=AMER&tier=GRANDMASTER_AND_CHAMPION

Saída gerada (mesma pasta do script):
  stats_inputs.csv  – dados de todos os personagens × todos os mapas
  maps.txt          – referência dos mapas competitivos até Neon Junction

Instalação (uma vez):
  pip install playwright
  playwright install chromium

Uso:
  python owtics_scraper.py

Notas:
  - Personagens/mapas recém-adicionados (Shion, Neon Junction etc.) podem
    não existir no site ainda → CSV recebe campos winrate/pickrate em branco.
  - O scraper aguarda o seletor real do site antes de extrair dados,
    baseado na estrutura HTML confirmada:
      span.flex-1.truncate          → nome do herói
      span.font-bold.tabular-nums   → winrate  (ex.: "55.7%")
      span.text-mute.tabular-nums   → pickrate (ex.: "7.0%")
"""

from __future__ import annotations

import csv
import logging
import re
import sys
import time
import random
import unicodedata
from pathlib import Path
from typing import Optional

import utils  # fonte única de heróis e mapas

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
REGION    = "AMER"
TIER      = "GRANDMASTER_AND_CHAMPION"
BASE_URL  = "https://owtics.gg/en-US/map"
DELAY_MIN = 2.0
DELAY_MAX = 4.0
TIMEOUT   = 40_000   # ms para page.goto

# Seletor que confirma que a página carregou com dados reais
# (baseado no HTML observado: cada herói tem um span.flex-1.truncate)
READY_SELECTOR = "span.flex-1.truncate"
READY_TIMEOUT  = 20_000  # ms

# ─────────────────────────────────────────────────────────────────────────────
#  Heróis e mapas — fonte única: utils.py
# ─────────────────────────────────────────────────────────────────────────────
PATCH = "Season 3 · 2026 (Reign of Talon: Into the Tiger's Den)"

# Mapas competitivos (nome, slug, modo) — vêm de utils.
MAPS: list[tuple[str, str, str]] = utils.MAPS_DATA

# ─────────────────────────────────────────────────────────────────────────────
#  Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def load_heroes() -> dict:
    """Heróis a partir de utils (fonte única)."""
    return {"version": "1.1.0", "patch": PATCH, "heroes": utils.load_heroes_roles()}


def hero_role_map(data: dict) -> dict[str, str]:
    return {h: role for role, heroes in data["heroes"].items() for h in heroes}


def all_heroes_list(data: dict) -> list[str]:
    return [h for heroes in data["heroes"].values() for h in heroes]


def slugify(name: str) -> str:
    """Normaliza nome para comparação tolerante a capitalização/pontuação/acentos."""
    s = re.sub(r"[:\.\'\`]", "", name)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def safe_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().rstrip("%")
        return float(value)
    except (ValueError, TypeError):
        return None


def fmt(value: Optional[float]) -> str:
    return f"{value:.2f}" if value is not None else ""

# ─────────────────────────────────────────────────────────────────────────────
#  JavaScript de extração — baseado no HTML real do owtics.gg
#
#  Estrutura confirmada por cada linha de herói:
#    <img alt="Roadhog" class="w-8 h-8 rounded-md …">
#    <span class="flex-1 text-sm text-foreground truncate">Roadhog</span>
#    <span class="w-14 … font-bold tabular-nums …">55.7%</span>   ← winrate
#    <span class="w-14 … text-xs tabular-nums text-mute …">7.0%</span>  ← pickrate
#
#  Estratégia:
#    1. Seleciona todos os span.flex-1.truncate  (um por herói)
#    2. Sobe para o elemento pai (a "linha" do herói)
#    3. No pai, busca os dois spans de percentual pelos seletores de classe
# ─────────────────────────────────────────────────────────────────────────────

_JS_OWTICS = r"""() => {
    const res = {};

    // Cada herói tem um span.flex-1.truncate com o nome
    const nameSpans = document.querySelectorAll('span.flex-1.truncate');

    for (const nameSpan of nameSpans) {
        const heroName = nameSpan.innerText.trim();
        if (!heroName || heroName.length < 2) continue;

        // O pai imediato é a "linha" do herói — contém os outros spans
        const row = nameSpan.parentElement;
        if (!row) continue;

        // Winrate: span com font-bold e tabular-nums (tem style color-mix)
        const wrEl = row.querySelector(
            'span.font-bold.tabular-nums, span[class*="font-bold"][class*="tabular-nums"]'
        );
        // Pickrate: span com text-mute e tabular-nums (menor, cinza)
        const prEl = row.querySelector(
            'span.text-mute.tabular-nums, span[class*="text-mute"][class*="tabular-nums"]'
        );

        const parse = el => {
            if (!el) return null;
            const v = parseFloat(el.innerText.trim().replace('%', ''));
            return isNaN(v) ? null : v;
        };

        const wr = parse(wrEl);
        const pr = parse(prEl);

        if (wr !== null || pr !== null) {
            res[heroName] = { winrate: wr, pickrate: pr };
        }
    }

    return res;
}"""


# Fallback XHR — intercepta respostas JSON da API interna do site
def extract_via_network(intercepted: list[dict]) -> dict[str, dict]:
    res: dict[str, dict] = {}

    def walk(obj):
        if isinstance(obj, dict):
            name = (obj.get("heroName") or obj.get("name")
                    or obj.get("hero")  or obj.get("character"))
            wr   = (obj.get("winRate")  or obj.get("winrate")  or obj.get("win_rate"))
            pr   = (obj.get("pickRate") or obj.get("pickrate") or obj.get("pick_rate"))
            if name and isinstance(name, str) and len(name) > 1:
                wr_f = safe_float(wr)
                pr_f = safe_float(pr)
                if wr_f is not None or pr_f is not None:
                    if wr_f is not None and wr_f < 1:
                        wr_f = round(wr_f * 100, 2)
                    if pr_f is not None and pr_f < 1:
                        pr_f = round(pr_f * 100, 2)
                    res[str(name)] = {"winrate": wr_f, "pickrate": pr_f}
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    for payload in intercepted:
        walk(payload)
    return res


# Fallback texto — último recurso
def extract_fallback_text(page) -> dict[str, dict]:
    text: str = page.evaluate("() => document.body.innerText")
    res: dict[str, dict] = {}
    pattern = re.compile(
        r"([A-ZÀ-Ö][^\n]{1,30}?)\s+"
        r"(\d{1,3}(?:\.\d+)?)\s*%\s+"
        r"(\d{1,3}(?:\.\d+)?)\s*%"
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        if len(name) < 2 or name.endswith("%"):
            continue
        res[name] = {"winrate": float(m.group(2)), "pickrate": float(m.group(3))}
    return res

# ─────────────────────────────────────────────────────────────────────────────
#  Scraping de um mapa
# ─────────────────────────────────────────────────────────────────────────────

def scrape_map(page, slug: str, name: str,
               intercepted: list[dict]) -> dict[str, dict]:
    """Retorna {hero_name: {winrate, pickrate}} ou {} se mapa indisponível."""
    url = f"{BASE_URL}/{slug}?region={REGION}&tier={TIER}"
    log.info(f"  GET {url}")

    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT)
    except Exception as e:
        log.warning(f"  {name}: erro ao carregar – {e}")
        return {}

    if resp and resp.status in (404, 410, 500, 503):
        log.warning(f"  {name}: HTTP {resp.status} – não disponível no site.")
        return {}

    # Aguarda o seletor real do site (confirmado via HTML observado)
    try:
        page.wait_for_selector(READY_SELECTOR, timeout=READY_TIMEOUT)
    except Exception:
        log.warning(f"  {name}: '{READY_SELECTOR}' não apareceu "
                    f"(mapa recente ou sem dados suficientes).")
        return {}

    # Pausa extra para garantir que todos os heróis foram renderizados
    page.wait_for_timeout(800)

    # ── Estratégia 1: JS direto no DOM (extração principal) ──────────────
    data: dict[str, dict] = page.evaluate(_JS_OWTICS)
    if data:
        log.info(f"  {name}: {len(data)} heróis (DOM owtics).")
        return data

    # ── Estratégia 2: resposta JSON interceptada na rede ─────────────────
    data = extract_via_network(intercepted)
    if data:
        log.info(f"  {name}: {len(data)} heróis (XHR/API).")
        return data

    # ── Estratégia 3: texto visível (último recurso) ─────────────────────
    data = extract_fallback_text(page)
    if data:
        log.info(f"  {name}: {len(data)} heróis (fallback text).")
        return data

    log.warning(f"  {name}: nenhum dado extraído.")
    return {}


def match_hero(hero: str, data: dict[str, dict]) -> Optional[dict]:
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

CSV_FIELDS = ["map", "map_type", "map_slug", "hero", "role", "winrate", "pickrate"]


def run():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright não instalado.")
        log.error("  Execute: pip install playwright && playwright install chromium")
        sys.exit(1)

    heroes_data = load_heroes()
    role_map    = hero_role_map(heroes_data)
    heroes      = all_heroes_list(heroes_data)

    log.info("=" * 62)
    log.info("OWTics Scraper v3.0")
    log.info(f"Patch  : {heroes_data.get('patch', '?')}")
    log.info(f"Heróis : {len(heroes)}")
    log.info(f"Mapas  : {len(MAPS)}")
    log.info(f"Região : {REGION}  |  Tier: {TIER}")
    log.info(f"Linhas CSV esperadas: {len(heroes) * len(MAPS)}")
    log.info("=" * 62)

    records: list[dict] = []
    intercepted_buf: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()

        # Intercepta respostas JSON (usado como fallback caso o DOM mude)
        def on_response(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                try:
                    intercepted_buf.append(response.json())
                except Exception:
                    pass

        page.on("response", on_response)

        # Bloqueia apenas fontes e vídeos — mantém imagens/SVG pois podem
        # ser necessários para o React renderizar os componentes corretamente
        page.route(
            re.compile(r"\.(woff2?|ttf|otf|mp4|mp3)(\?|$)"),
            lambda route: route.abort(),
        )

        for map_name, map_slug, map_type in MAPS:
            intercepted_buf.clear()
            log.info(f"\n[{map_type}] {map_name}")

            map_data = scrape_map(page, map_slug, map_name, list(intercepted_buf))

            for hero in heroes:
                stats    = match_hero(hero, map_data)
                wr_raw   = stats["winrate"]  if stats else None
                pr_raw   = stats["pickrate"] if stats else None

                records.append({
                    "map":      map_name,
                    "map_type": map_type,
                    "map_slug": map_slug,
                    "hero":     hero,
                    "role":     role_map.get(hero, "UNKNOWN"),
                    "winrate":  fmt(safe_float(wr_raw)),
                    "pickrate": fmt(safe_float(pr_raw)),
                })

            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            log.info(f"  Pausando {delay:.1f}s…")
            time.sleep(delay)

        page.close()
        context.close()
        browser.close()

    # ── Grava CSV ─────────────────────────────────────────────────
    out_csv = Path(__file__).parent / "stats_inputs.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    # ── Grava maps.txt ────────────────────────────────────────────
    out_maps = Path(__file__).parent / "maps.txt"
    with open(out_maps, "w", encoding="utf-8") as f:
        f.write("# Overwatch 2 – Mapas Competitivos (até Neon Junction)\n")
        f.write("# Exclui: 2CP (Assault) e Clash\n\n")
        current_mode = None
        for map_name, _, mode in MAPS:
            if mode != current_mode:
                current_mode = mode
                f.write(f"# ── {mode.upper()} {'─'*(50-len(mode))}\n")
            f.write(f"{map_name}\n")

    # ── Resumo ────────────────────────────────────────────────────
    total   = len(records)
    filled  = sum(1 for r in records if r["winrate"] != "")
    missing = total - filled

    log.info("\n" + "=" * 62)
    log.info(f"CSV salvo : {out_csv}")
    log.info(f"maps.txt  : {out_maps}")
    log.info(f"  Total de linhas : {total}")
    log.info(f"  Com dados       : {filled}")
    log.info(f"  Sem dados (NaN) : {missing}")
    if missing:
        miss_heroes = sorted({r["hero"] for r in records if r["winrate"] == ""})
        miss_maps   = sorted({r["map"]  for r in records if r["winrate"] == ""})
        log.info(f"  Heróis sem dados : {', '.join(miss_heroes)}")
        log.info(f"  Mapas sem dados  : {', '.join(miss_maps)}")
    log.info("=" * 62)
    log.info("Concluído!")


if __name__ == "__main__":
    run()
