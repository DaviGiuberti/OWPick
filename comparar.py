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
        base_path = sys._MEIPASS # Só existe quando vira .exe e extrai os arquivos para um pasta temporaria e esta variavel anota o caminho
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path) # Mostra o caminho final
 
templates_dir = Path(resource_path("heroes")) # Pasta empacatoda onde estão os templates de heróis, usamos resource_path

# A pasta 'print' continua relativa ao local de execução (não usa resource_path)
watch_dir = Path("print")
perks_names = ["0perk", "1perk", "2perk"]
output_filename = "lineup.txt"
target_size = (42, 42)             

# Carrega uma imagem e transforma em matriz numérica.
def load_image_gray(path, target_size=None): #abre a imagem e converte pra grayscale
    img = Image.open(path).convert("L")
    if target_size is not None:
        img = img.resize(target_size, Image.NEAREST) # redimensiona para 42x42 (os icons foram printados nessa resolução)
    arr = np.asarray(img, dtype=np.float32) #converte a imagem em vetor de float
    return arr

# Calcula o erro médio absoluto entre duas imagens.
def normalized_mae(a, b):
    mae = np.mean(np.abs(a - b))
    return mae / 255.0

# Carrega todas as imagens de heróis da pasta heroes.
def load_templates(templates_dir, target_size=(42,42)):
    templates = []
    if not templates_dir.exists():
        # Dica de debug caso esqueça de copiar a pasta no pyinstaller
        print(f"ERRO CRÍTICO: Pasta de templates não encontrada em: {templates_dir}") # Se a pasta não existir → erro crítico.
        raise RuntimeError(f"Pasta de templates não existe: {templates_dir}")
    
    for p in sorted(templates_dir.iterdir()): # Itera por todos os arquivos da pasta.
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}: # Filtra só imagens.
            arr = load_image_gray(p, target_size=target_size)
            templates.append((p.stem, arr))  # p.stem -> nome sem extensão. Guarda nome do heroi e imagem em forma de array
            
    if not templates: # Garante que pelo menos uma template foi carregada.
        raise RuntimeError(f"Nenhuma template encontrada em {templates_dir}")
    return templates

# Compara com todas as templates e escolhe a mais parecida
def find_best_match(img_arr, templates):
    best_name = None
    best_score = 1.0  # Score começa no pior valor possível.
    for name, tpl in templates: # Testa contra cada herói.
        if tpl.shape != img_arr.shape: # Garante que as imagens têm o mesmo tamanho.
            tpl_r = cv2.resize(tpl, (img_arr.shape[1], img_arr.shape[0]), interpolation=cv2.INTER_NEAREST)
        else:
            tpl_r = tpl
        score = normalized_mae(img_arr, tpl_r) # Calcula erro.
        if score < best_score: # Se achou algo melhor, atualiza o melhor resultado
            best_score = score
            best_name = name
    return best_name, best_score

# Analisa todas as imagens recortadas que foram printadas no jogo.
def process_folder(folder_path: Path, templates, target_size=(42,42)):
    folder_path.mkdir(parents=True, exist_ok=True)
    # Lista apenas imagens.
    files = [p for p in folder_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]
    files = sorted(files, key=lambda x: x.stat().st_mtime) # ordena por data de modificação.

    results = []  # lista de tuples (input_filename, matched_name, score)
    for p in files: 
        time.sleep(0.02) # evita acesso agressivo ao disco
        try:
            img = load_image_gray(p, target_size=target_size)
        except Exception as e:
            print(f"Falha ao abrir {p}: {e}  -> pulando")
            continue
        best_name, best_score = find_best_match(img, templates) # descobre qual herói essa imagem representa.
        results.append((p.name, best_name, best_score)) # guarda o resultado.
        #print(f"[{folder_path.name}] {p.name} -> {best_name} (score={best_score:.4f})")
    return results

# main
def executar():
    try:
        templates = load_templates(templates_dir, target_size=target_size) # Se falhar, aborta
    except RuntimeError as e:
        print(e)
        return

    # cria lista de pastas
    perk_paths = [watch_dir / name for name in perks_names]

    folder_stats = []  # lista de dicts: {path, results, avg_score}
    # processa imagens e calcula média do score
    # a com melhor media, quer dizer que é a pasta que os herois estão recortados de maneira correta
    for ppath in perk_paths:
        # Verifica se a pasta existe antes de processar
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

    # escolhe a pasta com menor erro médio.
    best = min(folder_stats, key=lambda x: x["avg_score"])
    if best["avg_score"] == math.inf: # caso nenhuma imagem exista, cria lineup.txt vazio
        # ATENÇÃO: Output file usa Path.cwd() para salvar onde o usuário está rodando, não na pasta temp
        out_file = Path.cwd() / output_filename
        out_file.write_text("", encoding="utf-8")
        print(f"Nenhuma imagem encontrada em nenhuma pasta. Criei lineup.txt vazio em {out_file.resolve()}")
        return

    best_path = best["path"]
    best_results = best["results"]

    # escreve lineup.txt no diretório atual (não na resource_path)
    out_file = Path.cwd() / output_filename
    with open(out_file, "w", encoding="utf-8") as f: # escrever lineup.txt, salva apenas os nomes dos heróis, um por linha.
        for input_filename, matched_name, score in best_results:
            f.write(f"{matched_name}\n")

    print(f"Melhor pasta: {best_path} (avg_score={best['avg_score']:.4f}).")
    # print(f"Gravado {len(best_results)} linhas em {out_file.resolve()}")

if __name__ == "__main__":
    executar()