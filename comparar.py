import time
from pathlib import Path
import math
import sys 
import os 
import cv2
import numpy as np
from PIL import Image

# Função "para executavel", mas tambem funciona no python normal
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
 
templates_dir = Path(resource_path("heroes"))
watch_dir = Path("print")
perks_names = ["0perk", "1perk", "2perk", "bug"]
output_filename = "lineup.txt"
target_size = (42, 42)             

# Carrega uma imagem e transforma em matriz numérica.
def load_image_gray(path, target_size=None):
    img = Image.open(path).convert("L")
    if target_size is not None:
        img = img.resize(target_size, Image.NEAREST)
    arr = np.asarray(img, dtype=np.float32)
    return arr

# Calcula o erro médio absoluto entre duas imagens.
def normalized_mae(a, b):
    mae = np.mean(np.abs(a - b))
    return mae / 255.0

# Carrega todas as imagens de heróis da pasta heroes.
def load_templates(templates_dir, target_size=(42,42)):
    templates = []
    if not templates_dir.exists():
        print(f"ERRO CRÍTICO: Pasta de templates não encontrada em: {templates_dir}")
        raise RuntimeError(f"Pasta de templates não existe: {templates_dir}")
    
    for p in sorted(templates_dir.iterdir()):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            arr = load_image_gray(p, target_size=target_size)
            templates.append((p.stem, arr))
            
    if not templates:
        raise RuntimeError(f"Nenhuma template encontrada em {templates_dir}")
    return templates

# NOVA FUNÇÃO: Template matching com busca vertical
def find_best_match_with_sliding(img_arr, templates, template_height=42):
    """
    Procura a melhor correspondência usando sliding window vertical.
    
    Args:
        img_arr: Imagem maior recortada (ex: 42x72 com buffer)
        templates: Lista de (nome, template_array)
        template_height: Altura do template (42)
    
    Returns:
        (best_name, best_score)
    """
    best_name = None
    best_score = 1.0
    
    img_height = img_arr.shape[0]
    img_width = img_arr.shape[1]
    
    # Se a imagem tem exatamente o tamanho do template, usa o método antigo
    if img_height == template_height:
        return find_best_match_old(img_arr, templates)
    
    # Caso contrário, faz sliding window vertical
    for name, tpl in templates:
        tpl_height, tpl_width = tpl.shape
        
        # Ajustar largura se necessário
        if tpl_width != img_width:
            tpl_resized = cv2.resize(tpl, (img_width, tpl_height), interpolation=cv2.INTER_NEAREST)
        else:
            tpl_resized = tpl
        
        # Sliding window: percorrer verticalmente
        max_offset = img_height - tpl_height
        if max_offset < 0:
            continue  # Template maior que imagem
        
        for offset in range(max_offset + 1):
            # Extrair janela da imagem
            window = img_arr[offset:offset+tpl_height, :]
            
            # Calcular score
            score = normalized_mae(window, tpl_resized)
            
            if score < best_score:
                best_score = score
                best_name = name
    
    return best_name, best_score

# Método antigo (mantido como fallback)
def find_best_match_old(img_arr, templates):
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

# Analisa todas as imagens recortadas
def process_folder(folder_path: Path, templates, target_size=(42,42)):
    folder_path.mkdir(parents=True, exist_ok=True)
    files = [p for p in folder_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]
    files = sorted(files, key=lambda x: x.stat().st_mtime)

    results = []
    for p in files: 
        time.sleep(0.02)
        try:
            # Carregar imagem SEM redimensionar (pode ser maior que 42x42)
            img = load_image_gray(p, target_size=None)
        except Exception as e:
            print(f"Falha ao abrir {p}: {e}  -> pulando")
            continue
        
        # Usar a nova função com sliding window
        best_name, best_score = find_best_match_with_sliding(img, templates, template_height=target_size[1])
        results.append((p.name, best_name, best_score))
        
    return results

# main
def executar():
    try:
        templates = load_templates(templates_dir, target_size=target_size)
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

        results = process_folder(ppath, templates, target_size=target_size)
        if results:
            scores = [r[2] for r in results]
            avg = float(np.mean(scores)) if scores else math.inf
        else:
            avg = math.inf
        folder_stats.append({"path": ppath, "results": results, "avg_score": avg})
        if not results:
            print(f" -> nenhuma imagem em {ppath}")

    # escolhe a pasta com menor erro médio
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

    print(f"Melhor pasta: {best_path} (avg_score={best['avg_score']:.4f}).")

if __name__ == "__main__":
    executar()