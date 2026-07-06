"""resolution.py — Matemática de resolução e recorte (pura, zero I/O).

Centraliza a conversão 720p / 1080p / 2K / outras por escala/interpolação
(sem tabelas por resolução), a escolha do banco de templates pelo TAMANHO do
retrato e a caixa de recorte da região do mapa. Recebe o config.json como
dict (lido pela infra) — não faz I/O.
"""

from __future__ import annotations

BASE_RESOLUTION = (1280, 720)  # resolução de referência (escala 1.0)
KNOWN_RESOLUTIONS = {  # pastas de templates disponíveis
    "720p": (1280, 720),
    "2k": (2560, 1440),
}

# Tamanho representativo (px) do retrato de cada banco de templates, medido na
# tela do jogo. É a régua usada para escolher o banco por proximidade de tamanho.
TEMPLATE_BANK_PORTRAIT_PX: dict[str, float] = {
    "720p": 41.0,  # retrato ~41x41 na tela em 720p (templates ~41px)
    "2k": 82.0,  # retrato ~82x82 na tela em 2K (templates ~82px)
}

# Tamanho-base (px, medido em 720p) do retrato do lineup (TAB+1). É escalado
# pela resolução atual antes de escolher o banco (template_bank_for_resolution).
# Obs.: os bans NÃO passam por esta escolha — usam o banco dedicado heroes/bans/
# (fonte de alta resolução, serve qualquer escala; ver matching.match_bans).
BASE_PORTRAIT_PX = 41.0  # retrato normal (TAB+1 / lineup) em 720p (~41px; em 2K ~82px)


def resolution_scale(full_w: int, base: tuple[int, int] = BASE_RESOLUTION) -> float:
    """Fator de escala linear da largura em relação à resolução base (720p)."""
    return full_w / base[0]


def nearest_resolution_key(
    full_w: int, full_h: int, resolutions: dict[str, tuple[int, int]] | None = None
) -> str | None:
    """
    Chave de resolução conhecida mais próxima da tela atual. Em caso de empate
    (ex.: 1080p é equidistante de 720p e 2K), prefere a MAIOR resolução —
    derivar de uma âncora de maior resolução tende a preservar mais qualidade.
    """
    resolutions = resolutions or KNOWN_RESOLUTIONS
    best_key, best_metric = None, None
    for key, (w, h) in resolutions.items():
        dist = (full_w - w) ** 2 + (full_h - h) ** 2
        metric = (dist, -(w * h))  # empate -> maior área primeiro
        if best_metric is None or metric < best_metric:
            best_metric, best_key = metric, key
    return best_key


def pick_template_bank(portrait_px: float, bank_sizes: dict[str, float] | None = None) -> str:
    """
    Escolhe o banco de templates cujo retrato representativo é o mais PRÓXIMO em
    tamanho de `portrait_px` (o tamanho, em px, do retrato que será comparado na
    resolução atual). Em caso de empate, prefere o banco de MAIOR resolução
    (mais qualidade), coerente com o desempate de nearest_resolution_key.

    Regra genérica, sem ifs por resolução: o limiar entre dois bancos é o ponto
    médio dos seus tamanhos representativos (≈61.5px para 41/82). Retratos
    menores usam 720p e maiores usam 2k, independentemente da resolução da tela.
    """
    bank_sizes = bank_sizes or TEMPLATE_BANK_PORTRAIT_PX
    best_key, best_metric = None, None
    for key, size in bank_sizes.items():
        metric = (abs(portrait_px - size), -size)  # empate -> maior tamanho (2k)
        if best_metric is None or metric < best_metric:
            best_metric, best_key = metric, key
    if best_key is None:
        raise ValueError("bank_sizes vazio: nenhum banco de templates para escolher")
    return best_key


def template_bank_for_resolution(full_w: int, base_portrait_px: float = BASE_PORTRAIT_PX) -> str:
    """
    Banco de templates recomendado para a resolução atual (`full_w`), para um
    retrato cujo tamanho em 720p é `base_portrait_px`. Escala o retrato pela
    resolução atual e delega a pick_template_bank.

    Ex.: em 1080p o retrato do lineup fica ~61.5px — mais próximo dos 82px do
    banco 2k do que dos 41px do 720p (empate resolvido para o 2k) — então o
    banco 2k é usado mesmo numa resolução intermediária.
    """
    return pick_template_bank(base_portrait_px * resolution_scale(full_w))


def scale_and_clamp(
    left_base: float,
    top_base: float,
    width_base: float,
    height_base: float,
    scale_x: float,
    scale_y: float,
    img_w: int,
    img_h: int,
) -> tuple[int, int, int, int]:
    """
    Função CANÔNICA de conversão de coordenadas de recorte: escala uma caixa
    definida na resolução-base por (scale_x, scale_y) e clampa nas bordas da
    imagem. Retorna (left, top, right, bottom) prontos para PIL.Image.crop.

    Usada tanto pelos recortes de retratos/bans (capture.py) quanto pela região
    do mapa (_region_to_box).
    """
    left = int(round(left_base * scale_x))
    top = int(round(top_base * scale_y))
    w = int(round(width_base * scale_x))
    h = int(round(height_base * scale_y))
    left = max(0, min(left, img_w - 1))
    top = max(0, min(top, img_h - 1))
    right = max(0, min(left + max(1, w), img_w))
    bottom = max(0, min(top + max(1, h), img_h))
    return (left, top, right, bottom)


def _region_to_box(
    region: dict, scale_x: float, scale_y: float, full_w: int, full_h: int
) -> tuple[int, int, int, int]:
    """Converte {left,top,width,height} (escalado) em caixa (l,t,r,b) clampada."""
    return scale_and_clamp(
        region["left"],
        region["top"],
        region["width"],
        region["height"],
        scale_x,
        scale_y,
        full_w,
        full_h,
    )


def get_scaled_map_region(
    full_w: int, full_h: int, config: dict
) -> tuple[int, int, int, int] | None:
    """
    Caixa de recorte (left, top, right, bottom) da região do nome do mapa para
    QUALQUER resolução, derivada matematicamente das âncoras de `config` (o
    conteúdo de config.json, lido pela infra):

      - resolução igual a uma âncora  -> usa as coordenadas nativas;
      - resolução ENTRE duas âncoras (ex.: 1080p entre 720p e 2K)
          -> interpola linearmente cada coordenada pela fração de largura;
      - resolução FORA do intervalo das âncoras
          -> escala proporcionalmente a partir da âncora mais próxima.
    """
    if not config:
        return None

    # Âncoras (base_w, entry) ordenadas por largura.
    anchors = []
    for entry in config.values():
        br = entry.get("base_resolution", {})
        if "map_region" in entry and br.get("width"):
            anchors.append((br["width"], br.get("height", full_h), entry["map_region"]))
    if not anchors:
        return None
    anchors.sort(key=lambda a: a[0])

    # Caso 1: dentro do intervalo -> interpola entre as duas âncoras vizinhas.
    for (w0, _h0, r0), (w1, _h1, r1) in zip(anchors, anchors[1:], strict=False):
        if w0 <= full_w <= w1 and w1 != w0:
            t = (full_w - w0) / (w1 - w0)
            region = {k: r0[k] + t * (r1[k] - r0[k]) for k in ("left", "top", "width", "height")}
            # As coordenadas já estão na escala da resolução atual.
            return _region_to_box(region, 1.0, 1.0, full_w, full_h)

    # Caso 2: fora do intervalo -> escala a partir da âncora mais próxima.
    base_w, base_h, region = min(anchors, key=lambda a: abs(a[0] - full_w))
    return _region_to_box(region, full_w / base_w, full_h / base_h, full_w, full_h)
