"""matching.py — Identificação de heróis por template matching (camada infra).

API principal (EM MEMÓRIA — o pipeline não passa mais pelo disco):
    match_lineup(cap)  -> (Lineup, {slot: MatchResult})
    match_bans(cap)    -> BanList

`executar()` mantém o fluxo antigo baseado em arquivos (lê print/, escreve
lineup.txt/bans.txt) reconstruindo um CaptureResult a partir do disco e
delegando às MESMAS funções — uma única implementação de matching.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from owpick import settings
from owpick.core import resolution
from owpick.core.models import BanList, CaptureResult, Hero, Lineup, MatchResult
from owpick.infra.resources import resource_path
from owpick.log import get_logger

log = get_logger("matching")

templates_base_dir = Path(resource_path(os.path.join("assets", "heroes")))
perks_names = ["0perk", "1perk", "2perk", "bug"]


def watch_dir() -> Path:
    """Pasta de entrada do fluxo CLI/debug: cache/print (resolvido em runtime)."""
    from owpick import paths

    return Path(paths.cache_file("print"))


output_filename = "lineup.txt"

BASE_CROP_SIZE = (42, 57)  # (largura, altura) do crop de entrada em 720p
BASE_WINDOW_HEIGHT = 42  # altura da janela/template em 720p

# Limiar de confiança do matching do LINEUP (escala 1 - CCOEFF_NORMED, 0-2;
# menor = melhor). Um slot cujo melhor score for MAIOR que isto é considerado
# NÃO identificado (hero=None, confident=False) e é excluído das somas de
# counter/sinergia — o modelo tolera listas menores. Análogo ao
# BAN_MATCH_MAX_SCORE dos bans.
#
# Calibração (fixtures 720p/1080p/2K, tarefa 1.4, métrica CCOEFF_NORMED da 4.2):
# os 30 slots com herói correto marcam no máximo 0.49 (1 - ccoeff, i.e. ccoeff
# 0.51; p95 ≈ 0.40). 0.70 fica com folga acima do pior match legítimo e abaixo
# de um slot sem retrato (lixo/vazio), cuja correlação despenca (ccoeff → 0 ⇒
# score → 1.0). NÃO usamos a margem (1º vs 2º) como critério de rejeição: as
# fixtures mostram matches corretos com margem pequena quando dois templates do
# MESMO herói são quase idênticos — margem baixa não implica erro, então
# rejeitar por margem geraria falso-negativo.
LINEUP_MATCH_MAX_SCORE = 0.70

FILE_TO_CATEGORY = {
    "ally1.png": "tank",
    "enemy1.png": "tank",
    "ally2.png": "dps",
    "ally3.png": "dps",
    "enemy2.png": "dps",
    "enemy3.png": "dps",
    "ally4.png": "sup",
    "ally5.png": "sup",
    "enemy4.png": "sup",
    "enemy5.png": "sup",
}

# --- Bans do competitivo -----------------------------------------------------
# Os ícones de ban usam uma ARTE DIFERENTE dos retratos do TAB+1: são os ícones
# 3D oficiais do herói (com moldura vermelha da UI), não os retratos ilustrados
# de heroes/720p|2k. Por isso existe um banco dedicado assets/heroes/bans/ (um
# .png de alta resolução por herói), que serve TODAS as resoluções: o matching
# é direto (sem janela deslizante, sem buffer), redimensionando recorte e
# templates para BAN_COMPARE_SIZE.
BANS_DIR_NAME = "bans"  # subpasta de print/ com os recortes de ban (debug/CLI)
BAN_TEMPLATES_DIR_NAME = "bans"  # subpasta de assets/heroes/ com os ícones oficiais
BANS_OUTPUT_FILENAME = "bans.txt"  # saída do fluxo CLI (executar)
BAN_COMPARE_SIZE = (48, 48)  # tamanho comum de comparação (recorte e templates)
BAN_FRAME_FRACTION = 0.05  # fração de cada borda descartada (moldura vermelha da UI)

# Limiar de confiança do matching de ban (MAE normalizado, 0-1). ÚNICO ponto de
# ajuste: um recorte cujo melhor MAE for MAIOR que isto é considerado slot VAZIO
# (sem herói banido) e ignorado. Calibrado em captura real 2K: herói correto
# marca 0.04-0.08 e o melhor match de um slot sem ban fica >= 0.15 — o limiar
# fica no meio desse vão. O score de cada slot vai para o log de debug.
BAN_MATCH_MAX_SCORE = 0.12


# ---------------------------------------------------------------------------
# Escala / templates
# ---------------------------------------------------------------------------
def compute_dims(scale: float, base_crop=BASE_CROP_SIZE, base_window_h=BASE_WINDOW_HEIGHT):
    """
    Dado o fator de escala, devolve:
      crop_size    = (largura, altura) esperada do recorte de entrada
      window_height = altura da janela deslizante (e dos templates)
    """
    crop_w = round(base_crop[0] * scale)
    crop_h = round(base_crop[1] * scale)
    window_h = round(base_window_h * scale)
    return (crop_w, crop_h), window_h


def to_gray_array(
    img: Image.Image, target_size=None, resample=Image.Resampling.NEAREST
) -> np.ndarray:
    """Converte uma imagem PIL em array cinza float32 (com resize opcional)."""
    img = img.convert("L")
    if target_size is not None:
        img = img.resize(target_size, resample)
    return np.asarray(img, dtype=np.float32)


def load_image_gray(path, target_size=None, resample=Image.Resampling.NEAREST):
    """Carrega um arquivo em escala de cinza (float32). NEAREST preserva o
    comportamento do TAB+1; o fluxo de bans usa LANCZOS (downscale do banco 128px)."""
    return to_gray_array(Image.open(path), target_size, resample)


def normalized_mae(a, b):
    return np.mean(np.abs(a - b)) / 255.0


def load_templates_from_category(templates_dir: Path, category: str, template_size):
    """Carrega templates redimensionados para (crop_w, window_height)."""
    category_dir = templates_dir / category
    templates = []
    if not category_dir.exists():
        print(f"AVISO: pasta de categoria não encontrada: {category_dir}")
        return templates
    for p in sorted(category_dir.iterdir()):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            arr = load_image_gray(p, target_size=template_size)
            templates.append((p.stem, arr))
    return templates


@lru_cache(maxsize=1)
def load_all_templates(templates_dir: Path, template_size):
    """
    Carrega o banco do lineup (tank/dps/sup) já em escala de cinza e
    redimensionado para `template_size`.

    Cacheado por `(templates_dir, template_size)`: em capturas sucessivas na
    MESMA resolução (o caso normal de vários TAB+1 seguidos) o banco inteiro
    não é relido/redimensionado de novo. Se a resolução mudar, `template_size`
    muda e a chave também — invalidação automática, sem estado manual.
    Os arrays retornados são tratados como imutáveis pelos consumidores.

    `maxsize=1` de propósito: uma sessão usa UM banco por vez (a resolução da
    janela do jogo não muda a cada captura). Guardar bancos antigos só manteria
    dezenas de MB de arrays residentes depois de um alt-tab entre tela cheia e
    modo janela — a próxima captura na resolução nova recarrega o banco certo e
    a anterior é liberada.
    """
    if not templates_dir.exists():
        raise RuntimeError(f"Pasta de templates não existe: {templates_dir}")

    templates_by_category = {}
    for category in ["tank", "dps", "sup"]:
        templates = load_templates_from_category(templates_dir, category, template_size)
        templates_by_category[category] = templates
        if not templates:
            print(f"AVISO: nenhum template em {category}")

    if not any(templates_by_category.values()):
        raise RuntimeError("Nenhum template encontrado em nenhuma categoria")

    return templates_by_category


# ---------------------------------------------------------------------------
# Matching com janela deslizante vertical (via cv2.matchTemplate)
# ---------------------------------------------------------------------------
def find_best_match_sliding(img_arr: np.ndarray, templates: list, window_height: int, crop_w: int):
    """
    Desliza cada template verticalmente sobre o recorte e devolve o de menor
    diferença (nome, score).

    Implementação em `cv2.matchTemplate` com `TM_CCOEFF_NORMED` (correlação
    cruzada normalizada de média zero): como o template tem a MESMA largura do
    recorte, o mapa de resultado é uma coluna — exatamente o deslizamento
    vertical do loop antigo, porém em C++/SIMD. O MÁXIMO do mapa (melhor
    correlação) substitui o loop de offsets.

    Por que média zero e normalizado (tarefa 4.2): o CCOEFF_NORMED subtrai a
    média e divide pelo desvio de cada janela, então é IMUNE a mudanças lineares
    de brilho/contraste (HDR, highlight do slot com hover, exposição). O score
    do OpenCV vive em [-1, 1] (1 = correlação perfeita); convertemos para
    `1 - ccoeff ∈ [0, 2]` para manter a convenção "menor = melhor" do resto do
    módulo (seleção de perk por min avg, limiar de confiança da 4.1).

    Decisão guiada pelos dados (fixtures 720p/1080p/2K, tarefa 1.4): CCOEFF_NORMED
    acerta os 30 slots (0 erros) e eleva a margem média de 0.0029 (TM_SQDIFF) para
    0.0238 — a margem MÍNIMA sai de 0.0000 (empate) para 0.0018. (TM_SQDIFF_NORMED
    foi descartado na 3.1 por divergir no 1080p.)
    """
    img_h, img_w = img_arr.shape

    if img_w != crop_w:
        img_arr = cv2.resize(img_arr, (crop_w, img_h), interpolation=cv2.INTER_NEAREST)
        img_h, img_w = img_arr.shape

    best_name = None
    best_score = math.inf

    for name, tpl in templates:
        t_h, t_w = tpl.shape
        search = img_arr
        # matchTemplate exige template <= imagem em ambas as dimensões; se o
        # recorte for menor que o template, amplia o recorte ao tamanho do
        # template (equivale ao ramo "sem janela" do algoritmo antigo).
        if t_h > img_h or t_w > img_w:
            search = cv2.resize(
                img_arr, (max(t_w, img_w), max(t_h, img_h)), interpolation=cv2.INTER_NEAREST
            )
        result = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)
        score = 1.0 - float(result.max())  # menor = melhor (1 - correlação)
        if score < best_score:
            best_score = score
            best_name = name

    return best_name, best_score


def _best_against_templates(img_arr, templates):
    best_name, best_score = None, 1.0
    for name, tpl in templates:
        if tpl.shape != img_arr.shape:
            tpl = cv2.resize(
                tpl, (img_arr.shape[1], img_arr.shape[0]), interpolation=cv2.INTER_NEAREST
            )
        score = normalized_mae(img_arr, tpl)
        if score < best_score:
            best_score = score
            best_name = name
    return best_name, best_score


# ---------------------------------------------------------------------------
# Lineup — matching EM MEMÓRIA sobre um CaptureResult
# ---------------------------------------------------------------------------
def _match_slots(
    crops: dict[str, Image.Image], templates_by_category, crop_size, window_height
) -> list[tuple[str, str | None, float]]:
    """Roda o matching de uma variação de perk. Slots em ordem explícita por
    nome (ally1..ally5, enemy1..enemy5) — a posição define aliado/inimigo."""
    crop_w = crop_size[0]
    results = []
    for slot_name in sorted(crops):
        category = FILE_TO_CATEGORY.get(slot_name)
        if category is None:
            continue
        templates = templates_by_category.get(category, [])
        if not templates:
            print(f"AVISO: nenhum template para {category} ({slot_name})")
            continue
        img_arr = to_gray_array(crops[slot_name])
        best_name, best_score = find_best_match_sliding(img_arr, templates, window_height, crop_w)
        log.debug("%s: match='%s' score=%.4f", slot_name, best_name, best_score)
        results.append((slot_name, best_name, best_score))
    return results


def lineup_templates_for(cap: CaptureResult):
    """Banco/dimensões de templates do lineup para a resolução da captura."""
    scale = resolution.resolution_scale(cap.width)
    crop_size, window_height = compute_dims(scale)
    template_size = (crop_size[0], window_height)
    res_folder = resolution.template_bank_for_resolution(cap.width, resolution.BASE_PORTRAIT_PX)
    log.debug(
        "resolução %dx%d escala %.4f banco=%s template_size=%s",
        cap.width,
        cap.height,
        scale,
        res_folder,
        template_size,
    )
    templates_by_category = load_all_templates(templates_base_dir / res_folder, template_size)
    return templates_by_category, crop_size, window_height


def match_lineup(cap: CaptureResult) -> tuple[Lineup, dict[str, MatchResult]]:
    """
    Identifica os heróis do lineup a partir dos recortes em memória.

    Cada variação de perk é avaliada; vence a de MENOR score médio. Retorna o
    Lineup (objetos Hero, normalização feita UMA vez na fronteira) e o
    MatchResult por slot.
    """
    templates_by_category, crop_size, window_height = lineup_templates_for(cap)

    best_results: list[tuple[str, str | None, float]] = []
    best_avg = math.inf
    best_perk = None
    for perk_name, crops in cap.portraits.items():
        results = _match_slots(crops, templates_by_category, crop_size, window_height)
        if not results:
            continue
        avg = float(np.mean([r[2] for r in results]))
        if avg < best_avg:
            best_avg, best_results, best_perk = avg, results, perk_name

    log.debug("melhor variação de perk: %s (avg_score=%.4f)", best_perk, best_avg)

    # Limiar efetivo: override do settings.json (avançado) ou o default
    # calibrado deste módulo (LINEUP_MATCH_MAX_SCORE).
    lineup_threshold = settings.get().lineup_match_max_score
    if lineup_threshold is None:
        lineup_threshold = LINEUP_MATCH_MAX_SCORE

    lineup = Lineup()
    slot_results: dict[str, MatchResult] = {}
    for slot_name, matched_name, score in best_results:
        # Limiar de confiança: um score acima de LINEUP_MATCH_MAX_SCORE indica que
        # o melhor template ainda está longe do recorte (slot sem retrato / lixo).
        # Nesse caso o slot é NÃO identificado e não entra no lineup — assim é
        # naturalmente excluído das somas de counter/sinergia (que iteram sobre
        # lineup.allies/enemies).
        confident = matched_name is not None and score <= lineup_threshold
        hero = Hero.from_name(matched_name) if (matched_name and confident) else None
        slot_results[slot_name] = MatchResult(hero=hero, score=score, confident=confident)
        if hero is None:
            log.debug(
                "%s: NÃO identificado (melhor='%s' score=%.4f > limiar %.2f)",
                slot_name,
                matched_name,
                score,
                lineup_threshold,
            )
            continue
        if slot_name.startswith("ally"):
            lineup.allies.append(hero)
        else:
            lineup.enemies.append(hero)
    return lineup, slot_results


# ---------------------------------------------------------------------------
# Bans do competitivo — matching DIRETO (sem janela deslizante, sem buffer)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_ban_templates(templates_dir: Path, template_size) -> list:
    """Carrega o banco dedicado de bans (assets/heroes/bans/, pasta plana).

    Cacheado por `(templates_dir, template_size)` — o banco de bans (fonte
    128px) é resolução-independente (template_size fixo em BAN_COMPARE_SIZE),
    então na prática é lido/redimensionado uma única vez por sessão. `maxsize=1`
    reflete isso: só existe uma chave possível no fluxo normal."""
    templates = []
    if not templates_dir.exists():
        print(f"AVISO: banco de bans não encontrado: {templates_dir}")
        return templates
    for p in sorted(templates_dir.iterdir()):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            arr = load_image_gray(p, target_size=template_size, resample=Image.Resampling.LANCZOS)
            templates.append((p.stem, arr))
    return templates


def _prepare_ban_crop(img: Image.Image) -> np.ndarray:
    """
    Prepara um recorte de ban para o matching direto: descarta a moldura
    vermelha da UI (BAN_FRAME_FRACTION por borda) e redimensiona o retrato
    restante para BAN_COMPARE_SIZE. Sem buffer nem janela deslizante — o slot
    de ban é fixo na UI, então o recorte já vem alinhado da captura.
    """
    img = img.convert("L")
    w, h = img.size
    margin = round(min(w, h) * BAN_FRAME_FRACTION)
    img = img.crop((margin, margin, w - margin, h - margin))
    img = img.resize(BAN_COMPARE_SIZE, Image.Resampling.LANCZOS)
    return np.asarray(img, dtype=np.float32)


def match_bans(cap: CaptureResult) -> BanList:
    """
    Detecta os heróis banidos nos 5 slots de ban do competitivo (em memória).

    Slot com melhor MAE acima de BAN_MATCH_MAX_SCORE é considerado vazio e
    ignorado. Sem repetições, na ordem dos slots.
    """
    if not cap.bans:
        return BanList()

    templates = load_ban_templates(templates_base_dir / BAN_TEMPLATES_DIR_NAME, BAN_COMPARE_SIZE)
    if not templates:
        return BanList()

    # Limiar efetivo: override do settings.json ou o default calibrado.
    ban_threshold = settings.get().ban_match_max_score
    if ban_threshold is None:
        ban_threshold = BAN_MATCH_MAX_SCORE

    banned = BanList()
    seen: set[str] = set()
    for slot_name in sorted(cap.bans):
        try:
            crop = _prepare_ban_crop(cap.bans[slot_name])
        except Exception as e:  # noqa: BLE001
            print(f"  {slot_name}: falha ao preparar ({e}) -> pulando")
            continue

        name, score = _best_against_templates(crop, templates)
        log.debug("%s: melhor='%s' score=%.4f (limiar %.2f)", slot_name, name, score, ban_threshold)
        if name is not None and score <= ban_threshold:
            hero = Hero.from_name(name)
            if hero.key not in seen:
                seen.add(hero.key)
                banned.heroes.append(hero)
    return banned


# ---------------------------------------------------------------------------
# Fluxo CLI baseado em arquivos (compatibilidade) — reconstrói o CaptureResult
# a partir de print/ e delega às MESMAS funções de matching em memória.
# ---------------------------------------------------------------------------
def load_capture_from_dir(watch: Path | None = None) -> CaptureResult | None:
    """Monta um CaptureResult a partir dos artefatos em print/ (full.png etc.)."""
    if watch is None:
        watch = watch_dir()
    full_path = watch / "full.png"
    if not full_path.exists():
        print(f"AVISO: {full_path} não encontrado.")
        return None
    try:
        with Image.open(full_path) as img:
            full = img.convert("RGB")
    except Exception as e:  # noqa: BLE001
        print(f"AVISO: falha ao ler {full_path}: {e}")
        return None

    portraits: dict[str, dict[str, Image.Image]] = {}
    for perk in perks_names:
        perk_dir = watch / perk
        if not perk_dir.is_dir():
            continue
        crops: dict[str, Image.Image] = {}
        for p in sorted(perk_dir.iterdir(), key=lambda x: x.name):
            if p.name in FILE_TO_CATEGORY:
                try:
                    with Image.open(p) as img:
                        crops[p.name] = img.convert("RGB")
                except Exception as e:  # noqa: BLE001
                    print(f"Falha ao abrir {p}: {e} -> pulando")
        if crops:
            portraits[perk] = crops

    bans: dict[str, Image.Image] = {}
    ban_dir = watch / BANS_DIR_NAME
    if ban_dir.is_dir():
        for i in range(1, 6):
            p = ban_dir / f"ban{i}.png"
            if p.exists():
                try:
                    with Image.open(p) as img:
                        bans[p.name] = img.convert("RGB")
                except Exception as e:  # noqa: BLE001
                    print(f"  ban{i}: falha ao abrir ({e}) -> pulando")

    return CaptureResult(full=full, resolution=full.size, portraits=portraits, bans=bans)


def executar():
    """Fluxo antigo por arquivos: lê print/, escreve lineup.txt e bans.txt."""
    from owpick.infra import storage

    cap = load_capture_from_dir()
    if cap is None:
        storage.write_lineup([])
        return

    # Bans ANTES do lineup — bans.txt é sempre reescrito (evita bans obsoletos).
    try:
        banned = match_bans(cap)
    except Exception as e:  # noqa: BLE001
        log.warning("falha ao processar bans", exc_info=True)
        print(f"AVISO: falha ao processar bans: {e}")
        banned = BanList()
    storage.write_bans(banned.names())
    if banned:
        print(f"Bans detectados: {', '.join(banned.names())}")
    else:
        print("Nenhum ban detectado (modo sem bans ou slots vazios).")

    try:
        lineup, slot_results = match_lineup(cap)
    except RuntimeError as e:
        print(e)
        return

    names = []
    for s in sorted(slot_results):
        hero = slot_results[s].hero
        names.append(hero.name if hero is not None else "")
    storage.write_lineup(names)
    log.debug("lineup.txt escrito (%d slots)", len(names))


if __name__ == "__main__":
    executar()
