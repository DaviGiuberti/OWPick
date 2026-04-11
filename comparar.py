import time
from pathlib import Path
import math
import sys 
import os 
import cv2
import numpy as np
from PIL import Image

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
 
templates_base_dir = Path(resource_path("heroes"))
watch_dir = Path("print")
perks_names = ["0perk", "1perk", "2perk", "bug"]
output_filename = "lineup.txt"

# Resoluções conhecidas e suas pastas correspondentes
KNOWN_RESOLUTIONS = {
    "720p": (1280, 720),
    "2k":   (2560, 1440),
}

BASE_RESOLUTION = (1280, 720)  # resolução de referência para target_size base
BASE_TARGET_SIZE = (42, 42)    # target_size correspondente à BASE_RESOLUTION
target_size = BASE_TARGET_SIZE  # fallback; sobrescrito dinamicamente via full.png

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

def get_target_size_from_full(watch_dir: Path,
                               base_size=BASE_TARGET_SIZE,
                               base_resolution=BASE_RESOLUTION):
    """
    Lê a resolução de full.png e escala o target_size proporcionalmente.
    Retorna base_size se full.png não existir ou falhar.
    """
    full_path = watch_dir / "full.png"
    if not full_path.exists():
        print(f"AVISO: {full_path} não encontrado; usando target_size padrão {base_size}")
        return base_size
    try:
        with Image.open(full_path) as img:
            w, h = img.size
        scale = w / base_resolution[0]
        tw = round(base_size[0] * scale)
        th = round(base_size[1] * scale)
        print(f"full.png detectado: {w}x{h} (escala {scale:.3f}) -> target_size = ({tw}, {th})")
        return (tw, th)
    except Exception as e:
        print(f"AVISO: Falha ao ler {full_path}: {e}; usando target_size padrão {base_size}")
        return base_size

def detect_screenshot_resolution(watch_dir: Path, perks_names: list):
    """
    Lê uma imagem qualquer das subpastas de prints e retorna sua resolução (width, height).
    Retorna None se não encontrar nenhuma imagem.
    """
    for perk in perks_names:
        perk_path = watch_dir / perk
        if not perk_path.exists():
            continue
        for p in perk_path.iterdir():
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
                try:
                    with Image.open(p) as img:
                        return img.size  # (width, height)
                except Exception:
                    continue
    return None

def find_nearest_resolution_folder(resolution, known_resolutions):
    """
    Dada uma resolução (width, height), retorna o nome da pasta mais próxima
    com base na distância euclidiana entre os pixels totais.
    """
    if resolution is None:
        # Fallback para 720p se não encontrar nenhuma imagem
        return "720p"

    w, h = resolution
    best_folder = None
    best_dist = math.inf

    for folder_name, (kw, kh) in known_resolutions.items():
        dist = math.sqrt((w - kw) ** 2 + (h - kh) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_folder = folder_name

    # print(f"Resolução detectada: {w}x{h} -> pasta '{best_folder}' (dist={best_dist:.0f})")
    return best_folder

def load_image_gray(path, target_size=None):
    img = Image.open(path).convert("L")
    if target_size is not None:
        img = img.resize(target_size, Image.NEAREST)
    arr = np.asarray(img, dtype=np.float32)
    return arr

def normalized_mae(a, b):
    mae = np.mean(np.abs(a - b))
    return mae / 255.0

def load_templates_from_category(templates_dir, category, target_size=(42,42)):
    category_dir = templates_dir / category
    templates = []
    if not category_dir.exists():
        print(f"AVISO: Pasta de categoria não encontrada: {category_dir}")
        return templates
    for p in sorted(category_dir.iterdir()):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            arr = load_image_gray(p, target_size=target_size)
            templates.append((p.stem, arr))
    return templates

def load_all_templates(templates_dir, target_size=(42,42)):
    if not templates_dir.exists():
        print(f"ERRO CRÍTICO: Pasta de templates não encontrada em: {templates_dir}")
        raise RuntimeError(f"Pasta de templates não existe: {templates_dir}")
    
    templates_by_category = {}
    for category in ["tank", "dps", "sup"]:
        templates = load_templates_from_category(templates_dir, category, target_size)
        if templates:
            templates_by_category[category] = templates
        else:
            print(f"AVISO: Nenhum template encontrado em {category}")
            templates_by_category[category] = []
    
    if not any(templates_by_category.values()):
        raise RuntimeError(f"Nenhuma template encontrada em nenhuma categoria")
    
    return templates_by_category

def find_best_match_with_sliding(img_arr, templates, template_height=42):
    best_name = None
    best_score = 1.0
    img_height = img_arr.shape[0]
    img_width = img_arr.shape[1]

    if img_height == template_height:
        return find_best_match_simple(img_arr, templates)

    for name, tpl in templates:
        tpl_height, tpl_width = tpl.shape
        if tpl_width != img_width:
            tpl_resized = cv2.resize(tpl, (img_width, tpl_height), interpolation=cv2.INTER_NEAREST)
        else:
            tpl_resized = tpl
        max_offset = img_height - tpl_height
        if max_offset < 0:
            continue
        for offset in range(max_offset + 1):
            window = img_arr[offset:offset+tpl_height, :]
            score = normalized_mae(window, tpl_resized)
            if score < best_score:
                best_score = score
                best_name = name

    return best_name, best_score

def find_best_match_simple(img_arr, templates):
    best_name = None
    best_score = 1.0
    for name, tpl in templates:
        if tpl.shape != img_arr.shape:
            tpl_r = cv2.resize(tpl, (img_arr.shape[1], img_arr.shape[0]), interpolation=cv2.INTER_NEAREST)
        else:
            tpl_r = tpl
        score = normalized_mae(img_arr, tpl_r)
        if score < best_score:
            best_score = score
            best_name = name
    return best_name, best_score

def process_folder(folder_path: Path, templates_by_category, target_size=(42,42)):
    folder_path.mkdir(parents=True, exist_ok=True)
    files = [p for p in folder_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]
    files = sorted(files, key=lambda x: x.stat().st_mtime)

    results = []
    for p in files: 
        time.sleep(0.02)
        category = FILE_TO_CATEGORY.get(p.name)
        if category is None:
            continue
        templates = templates_by_category.get(category, [])
        if not templates:
            print(f"AVISO: Nenhum template para categoria {category} (arquivo {p.name})")
            continue
        try:
            img = load_image_gray(p, target_size=None)
        except Exception as e:
            print(f"Falha ao abrir {p}: {e}  -> pulando")
            continue
        best_name, best_score = find_best_match_with_sliding(img, templates, template_height=target_size[1])
        results.append((p.name, best_name, best_score))
        
    return results

def executar():
    # 1. Determinar target_size a partir de full.png
    target_size = get_target_size_from_full(watch_dir)

    # 2. Detectar resolução e escolher subpasta de templates
    resolution = detect_screenshot_resolution(watch_dir, perks_names)
    res_folder = find_nearest_resolution_folder(resolution, KNOWN_RESOLUTIONS)
    templates_dir = templates_base_dir / res_folder  # ex: heroes/720p ou heroes/2k

    try:
        templates_by_category = load_all_templates(templates_dir, target_size=target_size)
    except RuntimeError as e:
        print(e)
        return

    perk_paths = [watch_dir / name for name in perks_names]

    folder_stats = []
    for ppath in perk_paths:
        if not ppath.exists() or not ppath.is_dir():
            print(f"Pasta ausente (pulando): {ppath}")
            folder_stats.append({"path": ppath, "results": [], "avg_score": math.inf})
            continue

        results = process_folder(ppath, templates_by_category, target_size=target_size)
        if results:
            scores = [r[2] for r in results]
            avg = float(np.mean(scores)) if scores else math.inf
        else:
            avg = math.inf
        folder_stats.append({"path": ppath, "results": results, "avg_score": avg})
        if not results:
            print(f" -> nenhuma imagem em {ppath}")

    best = min(folder_stats, key=lambda x: x["avg_score"])
    if best["avg_score"] == math.inf:
        out_file = Path.cwd() / output_filename
        out_file.write_text("", encoding="utf-8")
        print(f"Nenhuma imagem encontrada em nenhuma pasta. Criei lineup.txt vazio em {out_file.resolve()}")
        return

    best_path = best["path"]
    best_results = best["results"]

    out_file = Path.cwd() / output_filename
    with open(out_file, "w", encoding="utf-8") as f:
        for input_filename, matched_name, score in best_results:
            f.write(f"{matched_name}\n")

if __name__ == "__main__":
    executar()