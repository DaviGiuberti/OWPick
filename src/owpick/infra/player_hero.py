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

import re
import unicodedata
from collections.abc import Callable

import cv2
import numpy as np
from PIL import ImageOps
from PIL.Image import Image, fromarray
from rapidfuzz import fuzz, process

from owpick.core import resolution
from owpick.core.heroes import HERO_NAME_PUNCTUATION, get_all_heroes
from owpick.core.models import Hero
from owpick.infra import datasource, map_detect, ocr_backends
from owpick.log import get_logger

log = get_logger("player_hero")

# Região (coordenadas na base 720p) do NOME do herói do jogador na scoreboard.
# Escalada para a resolução atual pela MESMA matemática dos demais recortes
# (resolution.scale_and_clamp a partir da base_resolution do layout), então
# funciona em 720p/1080p/2K/4K sem lógica por resolução. Fallback usado só se o
# layout não trouxer a seção player_hero (nunca deveria — é empacotado).
_FALLBACK_NAME_REGION = {"left": 789, "top": 238, "width": 130, "height": 39}

# Um token do OCR só é "nome" se tiver ao menos um alfanumérico. O badge de role
# ao lado do nome vira lixo puramente simbólico ("&", "@", "@&") e é descartado
# antes do fuzzy match — ver _strip_upper.
_ALNUM = re.compile(r"[A-Z0-9]")

# Confiança mínima do fuzzy match do nome (escala do fuzz.token_set_ratio, 0-100).
# Calibração: simulando o OCR (maiúsculas, sem acento/pontuação, com o artefato do
# badge de role ao lado) para TODOS os heróis, o nome correto vence sempre (0 erros).
# Desde que _strip_upper passou a descartar a pontuação (v1.2.12), o nome lido
# limpo marca 100 em todos — a folga até o limiar é o que absorve o ruído do badge
# em baixa resolução (ex.: 720p lendo "DVS" por "D.VA": 66.7, 2º em 36.4). 60
# aceita reads parciais/ruidosos e ainda rejeita lixo de OCR — que cai no fallback
# (role manual), nunca numa role errada.
MIN_CONFIDENCE = 60.0

# Limiar dos pré-processos ALTERNATIVOS (v1.2.15 — ver _OCR_RECIPES). Mais alto
# de propósito: se o pré-processo calibrado não achou nome nenhum, a leitura é
# difícil, e sobrescrever a role manual com um palpite marginal é pior do que
# cair no fallback. Calibração nas 9 fixtures: quando um recipe alternativo lê o
# nome CERTO ele marca 91-100 (Mei 100, D.Va 100, Hanzo 100, Mizuki 91); quando
# erra, marca no máximo 55 (Sombra 50, Symmetra 53, Bastion 46). 80 fica no meio
# de uma faixa vazia larga.
MIN_CONFIDENCE_FALLBACK = 80.0

# Pré-processo alternativo (contraste local): parâmetros do CLAHE do OpenCV e do
# upscale/margem aplicados antes da binarização — ver _local_contrast_binary.
_CLAHE_CLIP_LIMIT = 3.0
_CLAHE_TILE_GRID = (8, 8)
_LOCAL_CONTRAST_UPSCALE = 3
# Margem branca ao redor da imagem binarizada: o Tesseract espera "quiet zone"
# em volta do texto e degrada quando os glifos encostam na borda do recorte.
_QUIET_ZONE_PX = 25


def _strip_upper(s: str) -> str:
    """Maiúsculas, sem acentos (NFKD) e sem pontuação — para o fuzzy match.

    Mantém os espaços (ao contrário de core.heroes.normalize_hero_name, que troca
    não-alfanuméricos por '-') porque o token_set_ratio compara CONJUNTOS de
    tokens separados por espaço: assim o ruído do OCR ao lado do nome (ex.: o badge
    de role lido como um token extra) não contamina o token do nome do herói.

    A pontuação dos nomes canônicos (HERO_NAME_PUNCTUATION: `. : ' \\``) é REMOVIDA
    dos dois lados da comparação (v1.2.12). Ela não é informação que o OCR consiga
    produzir de forma confiável — o Tesseract raramente enxerga o ponto de "D.Va" —
    e, em nomes CURTOS, cada caractere impossível de ler custa muitos pontos no
    ratio. Era a causa-raiz do bug do 720p: a região do nome inclui o badge de role,
    que em baixa resolução é lido COLADO ao nome ("DVS"); contra "D.VA" isso dava
    57.1 (< MIN_CONFIDENCE) e a role caía para o fallback manual. Sem a pontuação,
    "DVS" vs "DVA" dá 66.7 (2º colocado em 36.4 — margem larga).

    Tokens **sem nenhum alfanumérico** também são descartados (v1.2.13). O badge
    de role nem sempre gruda no nome: quando o Tesseract o isola, ele vira um
    token simbólico ("&", "@", "@&") que **infla o comprimento da frase** e derruba
    o `token_set_ratio` justamente nos nomes curtos. Era o caso da fixture
    `1080p/full3.png`, onde o OCR lê `"OVA &"` (o "D" sai como "O", confusão comum
    na fonte itálica do jogo): contra "DVA" isso dava **50.0**, abaixo do limiar,
    e a role caía de novo para o fallback manual. Sem o token "&", `"OVA"` vs
    `"DVA"` dá **66.7** e a detecção volta a funcionar. Nenhum nome canônico tem
    token puramente simbólico, então o filtro **nunca** altera o lado dos
    candidatos — só limpa o texto do OCR.

    O ganho é geral, não específico da D.Va: com o OCR lendo o nome limpo, TODOS
    os heróis de HEROES_ROLES passam a marcar 100 (antes o pior caso era D.Va
    85.7 e "Soldier: 76" 95.2).
    """
    s = HERO_NAME_PUNCTUATION.sub("", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(token for token in s.upper().split() if _ALNUM.search(token))


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


def _local_contrast_binary(img: Image) -> Image:
    """Pré-processo alternativo: contraste LOCAL + binarização de Otsu.

    O pré-processo padrão (map_detect.preprocess_for_ocr) estica o contraste da
    região INTEIRA de uma vez. Quando o recorte é quase todo preto e tem um único
    ponto muito claro — o badge de role, que em algumas telas é o pixel mais
    brilhante do recorte — o autocontraste global é dominado por esse ponto e o
    nome, que é só um pouco mais claro que o fundo, continua cinza. O Tesseract
    então binariza esse cinza contra o fundo e não acha texto nenhum: devolve "".

    O CLAHE equaliza o contraste por LADRILHO, então o brilho do badge não afeta
    mais a vizinhança do nome; o Otsu escolhe o corte pelo histograma já
    equalizado; e a inversão entrega texto PRETO sobre fundo BRANCO, que é o
    formato em que o Tesseract foi treinado. O upscale entra ANTES da binarização
    (interpolar tons dá bordas mais suaves do que ampliar pixels já binários).
    """
    gray = np.array(img.convert("L"))
    equalized = cv2.createCLAHE(clipLimit=_CLAHE_CLIP_LIMIT, tileGridSize=_CLAHE_TILE_GRID).apply(
        gray
    )
    height, width = equalized.shape
    upscaled = cv2.resize(
        equalized,
        (width * _LOCAL_CONTRAST_UPSCALE, height * _LOCAL_CONTRAST_UPSCALE),
        interpolation=cv2.INTER_LANCZOS4,
    )
    _threshold, binary = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return ImageOps.expand(fromarray(binary), border=_QUIET_ZONE_PX, fill=255)


# Tentativas de leitura do nome, EM ORDEM. Cada uma é (pré-processo, psm, limiar):
# a primeira é exatamente a leitura calibrada de sempre, e as seguintes só rodam
# se a anterior não devolver um nome acima do seu limiar — no caminho feliz o
# custo continua sendo UMA chamada ao Tesseract.
#
# Por que existe uma segunda e uma terceira (v1.2.15): a fixture 2k/full2.jpg
# (jogador de Mei) é lida como "" pelo pré-processo padrão, com QUALQUER psm e com
# ou sem dicionário — não é um problema de fuzzy match, é a binarização interna do
# Tesseract falhando num recorte escuro (ver _local_contrast_binary). Como o
# resultado era None, o pipeline caía para a role manual (Roles.txt) e, com ela
# marcada em SUP, o ranking saía de Suporte enquanto o jogador estava de Mei.
# Com contraste local o mesmo recorte lê "MEI" e marca 100.
_OCR_RECIPES: tuple[tuple[str, Callable[[Image], Image] | None, int, float], ...] = (
    ("padrao", None, ocr_backends.DEFAULT_PSM, MIN_CONFIDENCE),
    ("contraste-local", _local_contrast_binary, ocr_backends.DEFAULT_PSM, MIN_CONFIDENCE_FALLBACK),
    (
        "contraste-local-esparso",
        _local_contrast_binary,
        ocr_backends.SPARSE_PSM,
        MIN_CONFIDENCE_FALLBACK,
    ),
)


def identify_hero(ocr_text: str) -> tuple[str, float]:
    """(nome_canônico, score) do herói mais provável para o texto do OCR.

    Uma única chamada a rapidfuzz.process.extractOne com fuzz.token_set_ratio
    (mesmo scorer do map_detect) sobre a lista canônica de heróis (get_all_heroes).
    O processor _strip_upper deixa o match tolerante a caixa/acentos sem remover os
    espaços (ver docstring de _strip_upper).
    """
    # Texto vazio — ou que sobra vazio depois de descartar pontuação e tokens
    # simbólicos (ex.: o OCR só pegou o badge, "&") — não casa com ninguém.
    if not ocr_text or not _strip_upper(ocr_text):
        return "", 0.0
    choices = get_all_heroes()
    result = process.extractOne(
        ocr_text, choices, scorer=fuzz.token_set_ratio, processor=_strip_upper
    )
    if result is None:
        return "", 0.0
    matched, best_score, _idx = result
    return matched, float(best_score)


def read_hero_name(full_img: Image) -> tuple[str, float]:
    """(nome_canônico, score) do herói lido na scoreboard — "" se nenhum passou.

    Percorre _OCR_RECIPES em ordem e PARA na primeira tentativa cujo nome atinja
    o limiar daquela tentativa. Cada tentativa reusa o mesmo recorte e o mesmo
    backend (map_detect.extract_text_from_image), trocando só o pré-processo e o
    psm — nada de OCR duplicado aqui.
    """
    region = name_region(*full_img.size)
    for recipe, preprocess, psm, threshold in _OCR_RECIPES:
        ocr_text = map_detect.extract_text_from_image(
            full_img, region, preprocess=preprocess, psm=psm
        )
        candidate, score = identify_hero(ocr_text)
        log.debug(
            "OCR do herói do jogador [%s]: %r | melhor: '%s' (score=%.1f, limiar=%.1f)",
            recipe,
            ocr_text,
            candidate,
            score,
            threshold,
        )
        if candidate and score >= threshold:
            return candidate, score
    return "", 0.0


def detect(full_img: Image) -> Hero | None:
    """Identifica o herói do jogador a partir da imagem completa (em memória).

    Retorna um Hero (com a role já resolvida em Hero.from_name) quando alguma das
    tentativas de leitura (read_hero_name) casa com um herói acima do limiar;
    caso contrário None — sinal para o pipeline usar a role manual (fallback).
    Degrada com segurança: qualquer falha vira None (o ranking continua com a
    role manual).
    """
    try:
        candidate, _score = read_hero_name(full_img)
        if candidate:
            return Hero.from_name(candidate)
    except Exception:  # noqa: BLE001 — degrada para o fallback (role manual)
        log.warning("falha na detecção automática do herói do jogador", exc_info=True)
    return None
