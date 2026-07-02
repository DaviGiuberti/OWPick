#!/usr/bin/env python3
import mss
import os
from PIL import Image

import utils


def executar():
    outdir = os.path.expanduser("print")
    os.makedirs(outdir, exist_ok=True)

    # --- configuração base (valores definidos para 1280x720) ---
    BASE_W, BASE_H = 1280, 720

    # MODIFICAÇÃO: Adicionar margem vertical para busca
    VERTICAL_BUFFER = 8  # pixels de margem acima e abaixo

    captures_template = [
        {'top':125, 'width':44, 'height':44, 'name':'ally1.png'},
        {'top':169, 'width':44, 'height':44, 'name':'ally2.png'},
        {'top':213, 'width':44, 'height':44, 'name':'ally3.png'},
        {'top':257, 'width':44, 'height':44, 'name':'ally4.png'},
        {'top':301, 'width':44, 'height':44, 'name':'ally5.png'},
        {'top':396, 'width':44, 'height':44, 'name':'enemy1.png'},
        {'top':440, 'width':44, 'height':44, 'name':'enemy2.png'},
        {'top':484, 'width':44, 'height':44, 'name':'enemy3.png'},
        {'top':528, 'width':44, 'height':44, 'name':'enemy4.png'},
        {'top':572, 'width':44, 'height':44, 'name':'enemy5.png'},
    ]

    # pastas + valor de left correspondentes (valores para 1280x720)
    perks = [
        ('0perk', 230),
        ('1perk', 217),
        ('bug', 212),
        ('2perk', 197),
    ]

    # --- Slots de ban do competitivo (parte superior da tela) ---
    # Coordenadas convertidas da referência 2K (÷2) para a base 1280x720, para
    # reutilizar o mesmo escalonamento (scale_x/scale_y) dos demais recortes.
    # Cada slot tem seu próprio 'left' (independente das variações de perk) e é
    # capturado UMA única vez. Slots vazios são descartados depois, no matching.
    bans_template = [
        {'left': 270.5, 'top': 14.0, 'width': 31.0, 'height': 30.5, 'name': 'ban1.png'},
        {'left': 311.5, 'top': 13.5, 'width': 32.0, 'height': 31.5, 'name': 'ban2.png'},
        {'left': 353.5, 'top': 13.5, 'width': 31.5, 'height': 31.5, 'name': 'ban3.png'},
        {'left': 395.0, 'top': 13.5, 'width': 31.5, 'height': 31.0, 'name': 'ban4.png'},
        {'left': 437.0, 'top': 13.5, 'width': 31.5, 'height': 31.0, 'name': 'ban5.png'},
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
                        return role
        except Exception as e:
            print(f"Erro ao ler Roles.txt: {e}.")
        return None

    role = read_role()

    # determinar quais arquivos pular com base no role
    skip_files = set()
    if role:
        if "DPS" in role:
            skip_files.add("ally2.png")
        elif "SUP" in role:
            skip_files.add("ally4.png")
        elif "TANK" in role:
            skip_files.add("ally1.png")
        elif "ALL" in role:
            skip_files.add("ally1.png")
    else:
        pass

    # 1) capturar a tela do monitor principal e salvar em print/full.png
    with mss.mss() as sct:
        monitor_index = 1 if len(sct.monitors) > 1 else 0
        monitor = sct.monitors[monitor_index]

        sct_img = sct.grab(monitor)
        full_img = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
        full_w, full_h = full_img.size
        full_path = os.path.join(outdir, "full.png")
        full_img.save(full_path)

    # calcular fatores de escala
    scale_x = full_w / BASE_W
    scale_y = full_h / BASE_H

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

        # DELETAR arquivos que seriam pulados (se existirem)
        if skip_files:
            for fname in skip_files:
                fpath = os.path.join(perk_dir, fname)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        print(f"Falha ao deletar {fpath}: {e}")

        saved_count = 0
        skipped_count = 0

        for c in captures_template:
            if c['name'] in skip_files:
                skipped_count += 1
                continue

            # MODIFICAÇÃO: Adicionar buffer vertical
            # Recortar área maior para permitir busca vertical
            top_with_buffer = c['top'] - (VERTICAL_BUFFER)
            height_with_buffer = c['height'] + (2 * VERTICAL_BUFFER)

            left, top, right, bottom = scale_and_clamp(
                left_base, top_with_buffer, c['width'], height_with_buffer, full_w, full_h
            )
            crop = full_img.crop((left, top, right, bottom))
            out_path = os.path.join(perk_dir, c['name'])
            crop.save(out_path)
            saved_count += 1

    # 3) recortar os slots de ban (uma única vez; não dependem de perk)
    bans_dir = os.path.join(outdir, "bans")
    os.makedirs(bans_dir, exist_ok=True)
    for b in bans_template:
        # mesmo buffer vertical dos demais recortes, para a busca por janela deslizante
        top_with_buffer = b['top'] - VERTICAL_BUFFER
        height_with_buffer = b['height'] + (2 * VERTICAL_BUFFER)

        left, top, right, bottom = scale_and_clamp(
            b['left'], top_with_buffer, b['width'], height_with_buffer, full_w, full_h
        )
        crop = full_img.crop((left, top, right, bottom))
        crop.save(os.path.join(bans_dir, b['name']))

if __name__ == "__main__":
    executar()