import time
from pathlib import Path
import math
import sys
import os
import cv2
import numpy as np
from PIL import Image

import utils
from utils import resource_path


templates_base_dir = Path(resource_path("heroes"))
watch_dir = Path("print")
perks_names = ["0perk", "1perk", "2perk", "bug"]
output_filename = "lineup.txt"

# Resolução: constantes centralizadas em utils (720p / 2k; 1080p e outras
# resolvidas por escala). KNOWN_RESOLUTIONS aqui = pastas de templates.
KNOWN_RESOLUTIONS = utils.KNOWN_RESOLUTIONS
BASE_RESOLUTION   = utils.BASE_RESOLUTION  # resolução de referência (720p)
BASE_CROP_SIZE    = (42, 57)     # (largura, altura) do crop de entrada em 720p
BASE_WINDOW_HEIGHT = 42          # altura da janela/template em 720p

FILE_TO_CATEGORY = {
    "ally1.png":  "tank",
    "enemy1.png": "tank",
    "ally2.png":  "dps",
    "ally3.png":  "dps",
    "enemy2.png": "dps",
    "enemy3.png": "dps",
    "ally4.png":  "sup",
    "ally5.png":  "sup",
    "enemy4.png": "sup",
    "enemy5.png": "sup",
}


# ---------------------------------------------------------------------------
# Resolução / escala
# ---------------------------------------------------------------------------

def get_full_resolution(watch_dir: Path):
    """Lê full.png e retorna (w, h), ou None se indisponível."""
    full_path = watch_dir / "full.png"
    if not full_path.exists():
        return None
    try:
        with Image.open(full_path) as img:
            return img.size
    except Exception as e:
        print(f"AVISO: falha ao ler {full_path}: {e}")
        return None


def get_scale_from_full(watch_dir: Path, base_resolution=BASE_RESOLUTION) -> float:
    """Lê full.png e retorna o fator de escala em relação à resolução base."""
    res = get_full_resolution(watch_dir)
    if res is None:
        print(f"AVISO: print/full.png não encontrado; usando escala 1.0 (720p)")
        return 1.0
    w, h = res
    scale = w / base_resolution[0]
    print(f"full.png detectado: {w}x{h} -> escala {scale:.4f}")
    return scale


def compute_dims(scale: float,
                 base_crop=BASE_CROP_SIZE,
                 base_window_h=BASE_WINDOW_HEIGHT):
    """
    Dado o fator de escala, devolve:
      crop_size    = (largura, altura) esperada do arquivo de entrada
      window_height = altura da janela deslizante (e dos templates)
    """
    crop_w    = round(base_crop[0]    * scale)
    crop_h    = round(base_crop[1]    * scale)
    window_h  = round(base_window_h   * scale)
    return (crop_w, crop_h), window_h


def detect_screenshot_resolution(watch_dir: Path, perks_names: list):
    for perk in perks_names:
        perk_path = watch_dir / perk
        if not perk_path.exists():
            continue
        for p in perk_path.iterdir():
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
                try:
                    with Image.open(p) as img:
                        return img.size
                except Exception:
                    continue
    return None


def find_nearest_resolution_folder(resolution, known_resolutions):
    if resolution is None:
        return "720p"
    w, h = resolution
    best_folder, best_dist = None, math.inf
    for folder_name, (kw, kh) in known_resolutions.items():
        dist = math.sqrt((w - kw) ** 2 + (h - kh) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_folder = folder_name
    return best_folder


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def load_image_gray(path, target_size=None):
    img = Image.open(path).convert("L")
    if target_size is not None:
        img = img.resize(target_size, Image.NEAREST)
    return np.asarray(img, dtype=np.float32)


def normalized_mae(a, b):
    return np.mean(np.abs(a - b)) / 255.0


def load_templates_from_category(templates_dir: Path, category: str,
                                  template_size):
    """
    Carrega templates redimensionados para (crop_w, window_height).
    template_size = (width, height) = (crop_w, window_h)
    """
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


def load_all_templates(templates_dir: Path, template_size):
    if not templates_dir.exists():
        raise RuntimeError(f"Pasta de templates não existe: {templates_dir}")

    templates_by_category = {}
    for category in ["tank", "dps", "sup"]:
        templates = load_templates_from_category(templates_dir, category,
                                                  template_size)
        templates_by_category[category] = templates
        if not templates:
            print(f"AVISO: nenhum template em {category}")

    if not any(templates_by_category.values()):
        raise RuntimeError("Nenhum template encontrado em nenhuma categoria")

    return templates_by_category


# ---------------------------------------------------------------------------
# Matching com janela deslizante vertical
# ---------------------------------------------------------------------------

def find_best_match_sliding(img_arr: np.ndarray,
                             templates: list,
                             window_height: int,
                             crop_w: int):
    img_h, img_w = img_arr.shape

    if img_w != crop_w:
        img_arr = cv2.resize(img_arr, (crop_w, img_h), interpolation=cv2.INTER_NEAREST)
        img_w = crop_w

    max_offset = img_h - window_height
    if max_offset < 0:
        img_resized = cv2.resize(img_arr, (crop_w, window_height),
                                 interpolation=cv2.INTER_NEAREST)
        name, score = _best_against_templates(img_resized, templates)
       # print(f"  [sliding] sem janela (img menor que template) -> "
             # f"match='{name}'  score={score:.4f}")
        return name, score

    best_name   = None
    best_score  = 1.0
    best_offset = 0

    for offset in range(max_offset + 1):
        window = img_arr[offset: offset + window_height, :]

        for name, tpl in templates:
            score = normalized_mae(window, tpl)
            if score < best_score:
                best_score  = score
                best_name   = name
                best_offset = offset

    # print(f"  [sliding] match='{best_name}'  score={best_score:.4f}  "
          #f"offset={best_offset}  (janela {best_offset}:{best_offset + window_height}  "
          #f"de {img_h}px  |  {max_offset + 1} posições testadas)")

    return best_name, best_score


def _best_against_templates(img_arr, templates):
    best_name, best_score = None, 1.0
    for name, tpl in templates:
        if tpl.shape != img_arr.shape:
            tpl = cv2.resize(tpl, (img_arr.shape[1], img_arr.shape[0]),
                             interpolation=cv2.INTER_NEAREST)
        score = normalized_mae(img_arr, tpl)
        if score < best_score:
            best_score = score
            best_name  = name
    return best_name, best_score


# ---------------------------------------------------------------------------
# Processar pasta
# ---------------------------------------------------------------------------

def process_folder(folder_path: Path, templates_by_category,
                   crop_size, window_height):
    folder_path.mkdir(parents=True, exist_ok=True)
    crop_w = crop_size[0]

    files = [p for p in folder_path.iterdir()
             if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]
    files = sorted(files, key=lambda x: x.stat().st_mtime)

    results = []
    for p in files:
        time.sleep(0.02)
        category = FILE_TO_CATEGORY.get(p.name)
        if category is None:
            continue
        templates = templates_by_category.get(category, [])
        if not templates:
            print(f"AVISO: nenhum template para {category} ({p.name})")
            continue
        try:
            img = load_image_gray(p, target_size=None)   # sem resize — tamanho original
        except Exception as e:
            print(f"Falha ao abrir {p}: {e} -> pulando")
            continue

        best_name, best_score = find_best_match_sliding(
            img, templates, window_height, crop_w
        )
        results.append((p.name, best_name, best_score))

    return results


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def executar():
    # 1. Escala a partir de full.png
    scale = get_scale_from_full(watch_dir)
    crop_size, window_height = compute_dims(scale)
    template_size = (crop_size[0], window_height)   # (crop_w, window_h)

    #print(f"crop_size={crop_size}  window_height={window_height}  "
          #f"template_size={template_size}")

    # 2. Escolher subpasta de templates pela resolução detectada nas prints
    # Seleciona a pasta de templates pela resolução REAL da tela (full.png),
    # via lógica centralizada em utils. Para 1080p (equidistante de 720p e 2k)
    # a regra de desempate escolhe 2k, e os templates são redimensionados pela
    # escala calculada acima — sem necessidade de uma pasta 1080p dedicada.
    full_res = get_full_resolution(watch_dir)
    if full_res is not None:
        res_folder = utils.nearest_resolution_key(full_res[0], full_res[1])
    else:
        res_folder = find_nearest_resolution_folder(
            detect_screenshot_resolution(watch_dir, perks_names), KNOWN_RESOLUTIONS
        )
    templates_dir = templates_base_dir / res_folder
    print(f"Pasta de templates: {res_folder}")

    try:
        templates_by_category = load_all_templates(templates_dir, template_size)
    except RuntimeError as e:
        print(e)
        return

    perk_paths  = [watch_dir / name for name in perks_names]
    folder_stats = []

    for ppath in perk_paths:
        if not ppath.exists() or not ppath.is_dir():
            print(f"Pasta ausente (pulando): {ppath}")
            folder_stats.append({"path": ppath, "results": [], "avg_score": math.inf})
            continue

        results = process_folder(ppath, templates_by_category,
                                  crop_size, window_height)
        avg = float(np.mean([r[2] for r in results])) if results else math.inf
        folder_stats.append({"path": ppath, "results": results, "avg_score": avg})

        if not results:
            print(f" -> nenhuma imagem em {ppath}")

    best = min(folder_stats, key=lambda x: x["avg_score"])

    out_file = Path.cwd() / output_filename
    if best["avg_score"] == math.inf:
        out_file.write_text("", encoding="utf-8")
        print(f"Nenhuma imagem encontrada. lineup.txt vazio em {out_file.resolve()}")
        return

    with open(out_file, "w", encoding="utf-8") as f:
        for input_filename, matched_name, score in best["results"]:
            f.write(f"{matched_name}\n")

    print(f"lineup.txt escrito em {out_file.resolve()} "
          f"(pasta: {best['path'].name}, avg_score: {best['avg_score']:.4f})")


if __name__ == "__main__":
    executar()