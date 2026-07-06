"""map_detect.py — Identificação automática do mapa atual (camada infra).

Captura a região do nome do mapa, aplica OCR (Tesseract) e identifica o mapa
mais provável via fuzzy matching contra core.heroes.get_map_names().

detect(full_img) -> MapDetection é a API do pipeline (em memória). executar()
mantém o fluxo CLI por arquivos (lê print/full.png, grava current_map.txt).

Se o OCR falhar ou a confiança ficar abaixo de MIN_CONFIDENCE, o resultado é
UNKNOWN e o MetaStrength fica neutro (0), sem quebrar o ranking.
"""

from __future__ import annotations

import os

from PIL import Image, ImageOps
from rapidfuzz import fuzz, process

from owpick import settings
from owpick.core import resolution
from owpick.core.heroes import get_map_search_index
from owpick.core.models import MapDetection
from owpick.infra import datasource, ocr_backends
from owpick.log import get_logger

log = get_logger("map")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
OUTPUT_FILE = "current_map.txt"
# Confiança mínima do fuzzy match do mapa (escala do fuzz.token_set_ratio, 0-100).
# Recalibrada na tarefa 4.4 junto com a troca de scorer: o token_set_ratio
# comprime a escala num read parcial correto, então o antigo 50.0 rejeitaria
# reads corretos marginais. Com a âncora 720p da região do mapa recalibrada na
# v1.2.0 (layout: 890→1055), as três fixtures leem o nome do mapa de verdade —
# 720p score 100, 1080p ~67, 2K 100 — e 30 mantém folga para reads parciais
# em resoluções interpoladas sem aceitar lixo de OCR.
MIN_CONFIDENCE = 30.0


def full_image_path() -> str:
    """Caminho do full.png no cache de debug (cache/print/full.png)."""
    from owpick import paths

    return paths.cache_file(os.path.join("print", "full.png"))


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def extract_text_from_image(full_img: Image.Image, region: tuple[int, int, int, int]) -> str:
    """Recorta a região do mapa (em memória), pré-processa e roda o OCR."""
    try:
        img = full_img.crop(region)
        # Pré-processamento: escala de cinza + autocontraste + upscale.
        img = img.convert("L")
        img = ImageOps.autocontrast(img)
        w, h = img.size
        img = img.resize((max(1, w * 2), max(1, h * 2)), Image.Resampling.LANCZOS)
        # OCR via backend selecionado (Tesseract padrão; ver infra/ocr_backends).
        return ocr_backends.run_ocr(img)
    except Exception as e:  # noqa: BLE001
        # Degradação segura: sem OCR o mapa vira UNKNOWN e o MetaStrength fica
        # neutro — o ranking continua funcionando.
        log.warning("falha no OCR", exc_info=True)
        print(f"[map_detect] AVISO: falha no OCR: {e}")
        return ""


def extract_text_from_region(img_path: str, region: tuple[int, int, int, int]) -> str:
    """Versão baseada em arquivo (fluxo CLI). '' em caso de falha."""
    try:
        with Image.open(img_path) as img:
            full = img.convert("RGB")
    except Exception as e:  # noqa: BLE001
        log.warning("falha ao abrir %s", img_path, exc_info=True)
        print(f"[map_detect] AVISO: falha ao abrir {img_path}: {e}")
        return ""
    return extract_text_from_image(full, region)


def identify_map(ocr_text: str, map_list: list[str] | None = None) -> tuple[str, float]:
    """
    Retorna (nome_canônico_do_mapa, score_de_confiança) via fuzzy matching.

    Uma ÚNICA chamada a rapidfuzz.process.extractOne com fuzz.token_set_ratio
    (tarefa 4.4): substitui a antiga explosão de get_all_substrings (2ⁿ−1
    combinações de palavras — custo exponencial e propenso a falso positivo com
    nomes curtos). O token_set_ratio compara os CONJUNTOS de tokens, então lida
    bem com o ruído da UI ("COMPETITIVE", "|", etc.) ao redor do nome do mapa.

    Suporte a idioma do cliente (tarefa 4.6): compara o OCR contra TODOS os nomes
    canônicos (inglês) E os aliases localizados (get_map_search_index) e devolve
    sempre o nome CANÔNICO — assim o cliente em PT-BR ("Rota 66") resolve para a
    chave do stats_inputs.csv. `map_list` (só nomes) é aceito por compat; None usa
    o índice com aliases.

    Decisão pelos dados (fixtures 1.4): token_set_ratio foi o único scorer a
    manter 1080p (Lijiang Tower) e 2K (Neon Junction) corretos — partial_ratio e
    WRatio deixavam nomes curtos (OASIS) vencerem o mapa certo por falso positivo.
    """
    if not ocr_text:
        return "", 0.0
    if map_list is None:
        index = get_map_search_index()
    else:
        index = {name: name for name in map_list}
    choices = list(index)
    if not choices:
        return "", 0.0
    # processor=str.upper roda em query E choices (match tolerante a caixa) sem
    # remover pontuação — default_process re-tokeniza no "|"/"-" do ruído da UI e
    # degrada o match do nome parcial. Mapeia o alias vencedor de volta ao canônico.
    result = process.extractOne(ocr_text, choices, scorer=fuzz.token_set_ratio, processor=str.upper)
    if result is None:
        return "", 0.0
    matched, best_score, _idx = result
    return index[matched], float(best_score)


# ---------------------------------------------------------------------------
# Detecção EM MEMÓRIA (pipeline) e ponto de entrada CLI
# ---------------------------------------------------------------------------
def detect(full_img: Image.Image) -> MapDetection:
    """Identifica o mapa a partir da imagem completa EM MEMÓRIA."""
    try:
        full_w, full_h = full_img.size
        region = resolution.get_scaled_map_region(full_w, full_h, datasource.load_capture_config())
        if region is None:
            print("[map_detect] AVISO: config.json sem região de mapa válida.")
            return MapDetection()

        ocr_text = extract_text_from_image(full_img, region)
        # map_list=None → usa o índice canônico + aliases por idioma (tarefa 4.6).
        candidate, candidate_score = identify_map(ocr_text)
        # Limiar efetivo: override do settings.json ou o default calibrado.
        min_confidence = settings.get().map_min_confidence
        if min_confidence is None:
            min_confidence = MIN_CONFIDENCE
        log.debug(
            "OCR bruto: %r | melhor: '%s' (score=%.1f, limiar=%.1f)",
            ocr_text,
            candidate,
            candidate_score,
            min_confidence,
        )
        if candidate and candidate_score >= min_confidence:
            return MapDetection(name=candidate, score=candidate_score)
        print(
            f"[map_detect] Confiança insuficiente "
            f"(texto OCR: '{ocr_text}', melhor: '{candidate}', "
            f"score={candidate_score:.1f})."
        )
    except Exception as e:  # noqa: BLE001
        # Degradação segura: mapa UNKNOWN -> MetaStrength neutro.
        log.warning("falha na identificação do mapa", exc_info=True)
        print(f"[map_detect] AVISO: falha na identificação do mapa: {e}")
    return MapDetection()


def executar() -> str:
    """
    Fluxo CLI: identifica o mapa a partir de print/full.png e grava em
    current_map.txt. Retorna o nome do mapa identificado (ou "UNKNOWN").
    """
    from owpick.infra import storage

    detection = MapDetection()
    full_image = full_image_path()

    if not os.path.exists(full_image):
        print(f"[map_detect] {full_image} não encontrado — mapa não identificado.")
    else:
        try:
            with Image.open(full_image) as img:
                full = img.convert("RGB")
            detection = detect(full)
        except Exception as e:  # noqa: BLE001
            log.warning("falha ao abrir %s", full_image, exc_info=True)
            print(f"[map_detect] AVISO: falha ao abrir {full_image}: {e}")

    try:
        storage.write_current_map(detection.name)
    except OSError as e:
        print(f"[map_detect] AVISO: não foi possível gravar {OUTPUT_FILE}: {e}")

    if detection.known:
        print(f"Mapa identificado: '{detection.name}'")
    else:
        print("Mapa não identificado")
    return detection.name


if __name__ == "__main__":
    executar()
