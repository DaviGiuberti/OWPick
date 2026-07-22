"""player_hero.py — Detecção automática do herói (e da role) do jogador.

Na scoreboard do TAB, logo abaixo do retrato grande do herói escolhido, o jogo
exibe o NOME do herói em texto. Este módulo lê esse nome por OCR (o MESMO backend
e pré-processamento do map_detect) e identifica o herói por fuzzy match contra
core.heroes. A role do herói identificado é usada pelo pipeline do TAB+1 no lugar
da role manual (Roles.txt); quando a identificação falha, o pipeline mantém a role
manual como fallback.

detect(full_img) -> Hero | None é a API consumida pelo pipeline (em memória).

Por que OCR do nome, e não template matching contra assets/heroes/2k: a arte do
retrato GRANDE da scoreboard tem enquadramento/zoom diferentes do busto pequeno
(84x80) do banco do lineup, então o template matching é não confiável — em
capturas reais (fixtures 720p/1080p/2K) o herói correto some no meio do ranking
de similaridade. O nome em texto, ao contrário, é lido de forma robusta pelo OCR
já existente (os três heróis das fixtures leem com fuzzy score 100).
"""

from __future__ import annotations

import unicodedata

from PIL.Image import Image
from rapidfuzz import fuzz, process

from owpick.core import resolution
from owpick.core.heroes import get_all_heroes
from owpick.core.models import Hero
from owpick.infra import datasource, map_detect
from owpick.log import get_logger

log = get_logger("player_hero")

# Região (coordenadas na base 720p) do NOME do herói do jogador na scoreboard.
# Escalada para a resolução atual pela MESMA matemática dos demais recortes
# (resolution.scale_and_clamp a partir da base_resolution do layout), então
# funciona em 720p/1080p/2K/4K sem lógica por resolução. Fallback usado só se o
# layout não trouxer a seção player_hero (nunca deveria — é empacotado).
_FALLBACK_NAME_REGION = {"left": 789, "top": 238, "width": 130, "height": 39}

# Confiança mínima do fuzzy match do nome (escala do fuzz.token_set_ratio, 0-100).
# Calibração: simulando o OCR (maiúsculas, sem acento/pontuação, com o artefato do
# badge de role ao lado) para os 52 heróis, o nome correto vence sempre (0 erros),
# com o pior caso (D.Va) em 67. Nas capturas reais os nomes leem com score 100. 60
# aceita reads parciais/ruidosos e ainda rejeita lixo de OCR — que cai no fallback
# (role manual), nunca numa role errada.
MIN_CONFIDENCE = 60.0


def _strip_upper(s: str) -> str:
    """Maiúsculas sem acentos (NFKD), preservando espaços — para o fuzzy match.

    Mantém os espaços (ao contrário de core.heroes.normalize_hero_name, que troca
    não-alfanuméricos por '-') porque o token_set_ratio compara CONJUNTOS de
    tokens separados por espaço: assim o ruído do OCR ao lado do nome (ex.: o badge
    de role lido como um token extra) não contamina o token do nome do herói.
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def name_region(full_w: int, full_h: int, layout: dict | None = None) -> tuple[int, int, int, int]:
    """Caixa de recorte (l, t, r, b) do nome do herói para a resolução atual.

    Escala linear a partir da base do layout via resolution.scale_and_clamp — o
    mesmo mecanismo usado pelos recortes de retratos/bans em capture.crop_capture.
    """
    if layout is None:
        layout = datasource.load_layout()
    region = layout.get("player_hero", {}).get("name_region", _FALLBACK_NAME_REGION)
    base = layout.get("base_resolution", {})
    base_w = base.get("width", 1280)
    base_h = base.get("height", 720)
    scale_x = full_w / base_w
    scale_y = full_h / base_h
    return resolution.scale_and_clamp(
        region["left"],
        region["top"],
        region["width"],
        region["height"],
        scale_x,
        scale_y,
        full_w,
        full_h,
    )


def identify_hero(ocr_text: str) -> tuple[str, float]:
    """(nome_canônico, score) do herói mais provável para o texto do OCR.

    Uma única chamada a rapidfuzz.process.extractOne com fuzz.token_set_ratio
    (mesmo scorer do map_detect) sobre a lista canônica de heróis (get_all_heroes).
    O processor _strip_upper deixa o match tolerante a caixa/acentos sem remover os
    espaços (ver docstring de _strip_upper).
    """
    if not ocr_text:
        return "", 0.0
    choices = get_all_heroes()
    result = process.extractOne(
        ocr_text, choices, scorer=fuzz.token_set_ratio, processor=_strip_upper
    )
    if result is None:
        return "", 0.0
    matched, best_score, _idx = result
    return matched, float(best_score)


def detect(full_img: Image) -> Hero | None:
    """Identifica o herói do jogador a partir da imagem completa (em memória).

    Retorna um Hero (com a role já resolvida em Hero.from_name) quando o OCR do
    nome casa com um herói acima de MIN_CONFIDENCE; caso contrário None — sinal
    para o pipeline usar a role manual (fallback). Degrada com segurança: qualquer
    falha vira None (o ranking continua com a role manual).
    """
    try:
        full_w, full_h = full_img.size
        region = name_region(full_w, full_h)
        # Reuso do OCR do mapa (crop + grayscale + autocontraste + upscale + OCR):
        # extract_text_from_image é genérico (recebe imagem + região), então serve
        # tanto o nome do mapa quanto o nome do herói — sem duplicar pré-processo.
        ocr_text = map_detect.extract_text_from_image(full_img, region)
        candidate, score = identify_hero(ocr_text)
        log.debug(
            "OCR do herói do jogador: %r | melhor: '%s' (score=%.1f, limiar=%.1f)",
            ocr_text,
            candidate,
            score,
            MIN_CONFIDENCE,
        )
        if candidate and score >= MIN_CONFIDENCE:
            return Hero.from_name(candidate)
    except Exception:  # noqa: BLE001 — degrada para o fallback (role manual)
        log.warning("falha na detecção automática do herói do jogador", exc_info=True)
    return None
