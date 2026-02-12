#!/usr/bin/env python3
import mss
import os
from PIL import Image


def executar():
    outdir = os.path.expanduser("print")
    os.makedirs(outdir, exist_ok=True)

    # --- configuração base (valores definidos para 1280x720) ---
    BASE_W, BASE_H = 1280, 720

    captures_template = [
        {'top':137, 'width':41, 'height':41, 'name':'ally1.png'},
        {'top':178, 'width':41, 'height':41, 'name':'ally2.png'},
        {'top':220, 'width':41, 'height':41, 'name':'ally3.png'},
        {'top':261, 'width':41, 'height':41, 'name':'ally4.png'},
        {'top':303, 'width':41, 'height':41, 'name':'ally5.png'},
        {'top':400, 'width':41, 'height':41, 'name':'enemy1.png'},
        {'top':441, 'width':41, 'height':41, 'name':'enemy2.png'},
        {'top':482, 'width':41, 'height':41, 'name':'enemy3.png'},
        {'top':523, 'width':41, 'height':41, 'name':'enemy4.png'},
        {'top':564, 'width':41, 'height':42, 'name':'enemy5.png'},
    ]

    # pastas + valor de left correspondentes (valores para 1280x720)
    perks = [
        ('0perk', 207),
        ('1perk', 203),
        ('2perk', 182),
        ('bug', 197),
    ]

    # --- Ler role a partir de Roles.txt (mesmo diretório do script) ---
    def read_role():
        role_path = "Roles.txt"
        if not os.path.exists(role_path):
            print("Role não encontrada. Escolha a sua Função")
            return None
        try:
            with open(role_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        role = line.upper()
                        #print(f"Função: '{role}'")
                        return role
        except Exception as e:
            print(f"Erro ao ler Roles.txt: {e}.")
        return None

    role = read_role()

    # determinar quais arquivos pular com base no role (tolerante a variações)
    skip_files = set()
    if role:
        if "DPS" in role:
            skip_files.add("ally2.png")
        elif "SUP" in role:   # pega SUPPORT, SUPORT, support etc.
            skip_files.add("ally4.png")
        elif "TANK" in role:
            skip_files.add("ally1.png")
        elif "ALL" in role:   # ALLROLES ou similar
            # mantendo a lógica anterior: ALLROLES também mapeava para ally1.png
            skip_files.add("ally1.png")
    else:
        # nenhum skip (Roles.txt ausente ou erro)
        pass

    # 1) capturar a tela do monitor principal e salvar em print/full.png
    with mss.mss() as sct:
        monitor_index = 1 if len(sct.monitors) > 1 else 0
        monitor = sct.monitors[monitor_index]
        # print(f"Usando monitor {monitor_index}: {monitor}")

        sct_img = sct.grab(monitor)
        full_img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
        full_w, full_h = full_img.size
        full_path = os.path.join(outdir, "full.png")
        full_img.save(full_path)
        # print(f"Full screenshot salva em: {full_path} (resolução detectada: {full_w}x{full_h})")

    # calcular fatores de escala (do base 1280x720 -> resolução atual)
    scale_x = full_w / BASE_W
    scale_y = full_h / BASE_H
    # print(f"Fatores de escala -> x: {scale_x:.4f}, y: {scale_y:.4f}")

    # função helper para converter e limitar coordenadas
    def scale_and_clamp(left_base, top_base, width_base, height_base, img_w, img_h):
        left = int(round(left_base * scale_x))
        top = int(round(top_base * scale_y))
        w = int(round(width_base * scale_x))
        h = int(round(height_base * scale_y))
        # clamp nas bordas da imagem
        left = max(0, min(left, img_w - 1))
        top = max(0, min(top, img_h - 1))
        right = max(0, min(left + max(1, w), img_w))
        bottom = max(0, min(top + max(1, h), img_h))
        return (left, top, right, bottom)

    # 2) recortar a partir da imagem inteira e salvar nas subpastas
    for perk_name, left_base in perks:
        perk_dir = os.path.join(outdir, perk_name)
        os.makedirs(perk_dir, exist_ok=True)

        # DELETAR arquivos que seriam pulados (se existirem) — conforme pedido
        if skip_files:
            for fname in skip_files:
                fpath = os.path.join(perk_dir, fname)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        #print(f"Deletado: {fpath}")
                    except Exception as e:
                        print(f"Falha ao deletar {fpath}: {e}")

        saved_count = 0
        skipped_count = 0

        for c in captures_template:
            if c['name'] in skip_files:
                skipped_count += 1
                continue

            left, top, right, bottom = scale_and_clamp(
                left_base, c['top'], c['width'], c['height'], full_w, full_h
            )
            crop = full_img.crop((left, top, right, bottom))
            out_path = os.path.join(perk_dir, c['name'])
            crop.save(out_path)
            saved_count += 1

        #print(f"Salvos {saved_count} recortes em: {perk_dir} (pulados/deletados: {skipped_count})")

    # --- NOVO BLOCO: Recorte da pasta MAP ---
    map_dir = os.path.join(outdir, "map")
    os.makedirs(map_dir, exist_ok=True)
    
    # Coordenadas base fornecidas
    map_base = {'left': 982, 'top': 19, 'width': 184, 'height': 26}
    # Aplicar escala e clamp
    m_left, m_top, m_right, m_bottom = scale_and_clamp(
        map_base['left'], map_base['top'], map_base['width'], map_base['height'], full_w, full_h
    )
    
    map_crop = full_img.crop((m_left, m_top, m_right, m_bottom))
    map_crop.save(os.path.join(map_dir, "map.png"))
    # ----------------------------------------

    # print("Pronto!")

if __name__ == "__main__":
    executar()