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
perks_names = ["0perk", "1perk", "2perk"]
output_filename = "lineup.txt"
target_size = (42, 42)

# MAPEAMENTO: arquivo -> categoria
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

# Carrega templates de uma subpasta específica (tank, dps ou sup)
def load_templates_from_category(templates_dir, category, target_size=(42,42)):
    """
    Carrega templates de uma categoria específica.
    
    Args:
        templates_dir: Path da pasta heroes
        category: "tank", "dps" ou "sup"
        target_size: Tamanho alvo para redimensionar
    
    Returns:
        Lista de (nome, array)
    """
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

# Carrega todas as categorias de templates
def load_all_templates(templates_dir, target_size=(42,42)):
    """
    Carrega templates de todas as categorias (tank, dps, sup).
    
    Returns:
        Dict com {categoria: [(nome, array), ...]}
    """
    if not templates_dir.exists():
        print(f"ERRO CRÍTICO: Pasta de templates não encontrada em: {templates_dir}")
        raise RuntimeError(f"Pasta de templates não existe: {templates_dir}")
    
    templates_by_category = {}
    
    for category in ["tank", "dps", "sup"]:
        templates = load_templates_from_category(templates_dir, category, target_size)
        if templates:
            templates_by_category[category] = templates
            #print(f"Carregados {len(templates)} templates de {category}")
        else:
            print(f"AVISO: Nenhum template encontrado em {category}")
            templates_by_category[category] = []
    
    if not any(templates_by_category.values()):
        raise RuntimeError(f"Nenhuma template encontrada em nenhuma categoria")
    
    return templates_by_category

# Template matching com busca vertical
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
    
    # Se a imagem tem exatamente o tamanho do template, usa o método simples
    if img_height == template_height:
        return find_best_match_simple(img_arr, templates)
    
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

# Método simples (quando imagem tem mesmo tamanho do template)
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

# Analisa todas as imagens recortadas COM CATEGORIAS
def process_folder(folder_path: Path, templates_by_category, target_size=(42,42)):
    """
    Processa pasta comparando cada imagem apenas com templates da sua categoria.
    
    Args:
        folder_path: Path da pasta (ex: print/0perk)
        templates_by_category: Dict {categoria: [(nome, array), ...]}
        target_size: Tamanho alvo
    
    Returns:
        Lista de (input_filename, matched_name, score)
    """
    folder_path.mkdir(parents=True, exist_ok=True)
    files = [p for p in folder_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]
    files = sorted(files, key=lambda x: x.stat().st_mtime)

    results = []
    for p in files: 
        time.sleep(0.02)
        
        # Determinar categoria baseado no nome do arquivo
        category = FILE_TO_CATEGORY.get(p.name)
        
        if category is None:
            # Arquivo não mapeado, pular
            #print(f"Pulando {p.name} (não mapeado para categoria)")
            continue
        
        # Pegar templates da categoria
        templates = templates_by_category.get(category, [])
        
        if not templates:
            print(f"AVISO: Nenhum template para categoria {category} (arquivo {p.name})")
            continue
        
        try:
            # Carregar imagem SEM redimensionar (pode ser maior que 42x42)
            img = load_image_gray(p, target_size=None)
        except Exception as e:
            print(f"Falha ao abrir {p}: {e}  -> pulando")
            continue
        
        # Comparar apenas com templates da categoria correta
        best_name, best_score = find_best_match_with_sliding(img, templates, template_height=target_size[1])
        results.append((p.name, best_name, best_score))
        
    return results

# main
def executar():
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

    #print(f"Melhor pasta: {best_path} (avg_score={best['avg_score']:.4f}).")

if __name__ == "__main__":
    executar()