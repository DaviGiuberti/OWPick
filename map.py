"""
map.py — Identificação automática do mapa atual.

Captura a região do nome do mapa em print/full.png, aplica OCR (Tesseract) e
identifica o mapa mais provável via fuzzy matching contra a lista de mapas de
utils.get_map_names(). O resultado é gravado em current_map.txt para ser lido
por choose_ow_hero.py.

Se o OCR falhar ou a confiança ficar abaixo de MIN_CONFIDENCE, current_map.txt
recebe "UNKNOWN" e o MetaStrength fica neutro (0) para todos os heróis, sem
quebrar o ranking.
"""

from __future__ import annotations

import itertools
import os
from typing import List, Tuple

from PIL import Image, ImageOps

import utils

try:
    import pytesseract
except Exception:  # noqa: BLE001 — OCR é opcional; degrada para UNKNOWN
    pytesseract = None

from rapidfuzz import fuzz


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
FULL_IMAGE = os.path.join("print", "full.png")
OUTPUT_FILE = "current_map.txt"
MIN_CONFIDENCE = 50.0  # score mínimo (0-100) para aceitar a identificação

# Caminho do Tesseract embutido (pasta ocr/) — resolvido para .py e .exe.
_TESSERACT_EXE = utils.resource_path(os.path.join("ocr", "tesseract.exe"))
_TESSDATA_DIR = utils.resource_path(os.path.join("ocr", "tessdata"))


def _configure_tesseract() -> bool:
    """Aponta o pytesseract para o Tesseract embutido. False se indisponível."""
    if pytesseract is None:
        return False
    if os.path.exists(_TESSERACT_EXE):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE
    # Aponta o Tesseract para a pasta tessdata embutida via variável de
    # ambiente (TESSDATA_PREFIX). Isso evita passar --tessdata-dir no config,
    # que corrompe caminhos com espaços/aspas e quebra o carregamento do idioma.
    if os.path.isdir(_TESSDATA_DIR):
        os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR
    return True


# ---------------------------------------------------------------------------
# Carregamento de mapas — fonte única: utils (não lê mais maps.txt)
# ---------------------------------------------------------------------------
def load_maps() -> List[str]:
    """Lista de mapas a partir de utils (fonte única de dados)."""
    return utils.get_map_names()


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def extract_text_from_region(img_path: str, region: Tuple[int, int, int, int]) -> str:
    """Recorta a região do mapa, pré-processa e roda o OCR. '' em caso de falha."""
    if not _configure_tesseract():
        return ""
    try:
        img = Image.open(img_path).crop(region)
        # Pré-processamento: escala de cinza + autocontraste + upscale.
        img = img.convert("L")
        img = ImageOps.autocontrast(img)
        w, h = img.size
        img = img.resize((max(1, w * 2), max(1, h * 2)), Image.LANCZOS)
        config = "--oem 3 --psm 7"
        return pytesseract.image_to_string(img, lang="eng", config=config).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[map.py] AVISO: falha no OCR: {e}")
        return ""


def get_all_substrings(text: str) -> List[str]:
    """Gera todas as combinações de palavras (preservando a ordem) do texto."""
    words = [w for w in text.split() if w]
    combos: List[str] = []
    for r in range(1, len(words) + 1):
        for combo in itertools.combinations(words, r):
            combos.append(" ".join(combo))
    return combos


def identify_map(ocr_text: str, map_list: List[str]) -> Tuple[str, float]:
    """Retorna (nome_do_mapa, score_de_confiança) via fuzzy matching."""
    substrings = get_all_substrings(ocr_text)
    if not substrings or not map_list:
        return "", 0.0

    best_map, best_score = "", 0.0
    for mapa in map_list:
        mapa_up = mapa.upper()
        for sub in substrings:
            score = fuzz.ratio(sub.upper(), mapa_up)
            if score > best_score:
                best_score = score
                best_map = mapa
    return best_map, best_score


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def executar() -> str:
    """
    Identifica o mapa atual e grava em current_map.txt.
    Retorna o nome do mapa identificado (ou "UNKNOWN").
    """
    mapa = "UNKNOWN"
    score = 0.0

    if not os.path.exists(FULL_IMAGE):
        print(f"[map.py] {FULL_IMAGE} não encontrado — mapa não identificado.")
    else:
        try:
            with Image.open(FULL_IMAGE) as full:
                full_w, full_h = full.size
            region = utils.get_scaled_map_region(full_w, full_h)
            if region is None:
                print("[map.py] AVISO: config.json sem região de mapa válida.")
            else:
                ocr_text = extract_text_from_region(FULL_IMAGE, region)
                map_list = load_maps()
                candidate, candidate_score = identify_map(ocr_text, map_list)
                if candidate and candidate_score >= MIN_CONFIDENCE:
                    mapa, score = candidate, candidate_score
                else:
                    print(
                        f"[map.py] Confiança insuficiente "
                        f"(texto OCR: '{ocr_text}', melhor: '{candidate}', "
                        f"score={candidate_score:.1f})."
                    )
        except Exception as e:  # noqa: BLE001
            print(f"[map.py] AVISO: falha na identificação do mapa: {e}")

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(mapa)
    except Exception as e:  # noqa: BLE001
        print(f"[map.py] AVISO: não foi possível gravar {OUTPUT_FILE}: {e}")

    if mapa != "UNKNOWN":
        print(f"[map.py] Mapa identificado: '{mapa}' (score={score:.1f})")
    else:
        print("[map.py] Mapa não identificado -> UNKNOWN")
    return mapa


if __name__ == "__main__":
    executar()
