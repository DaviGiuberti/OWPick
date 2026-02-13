"""
compararMapa.py - Map Reader com Tesseract OCR Embutido
Extrai o nome do mapa de screenshots do Overwatch 2
Versão: Tesseract incluído no executável
"""

import os
import sys
from pathlib import Path
from PIL import Image
import pytesseract
from rapidfuzz import process, fuzz
from unidecode import unidecode
import re

# ============================================================================
# CONFIGURAÇÃO DO TESSERACT PARA PYINSTALLER (TESSERACT EMBUTIDO)
# ============================================================================

def configure_tesseract():
    """
    Configura o Tesseract OCR para funcionar tanto como script quanto como executável.
    Esta versão assume que o Tesseract está na pasta 'ocr' ao lado do script.
    """
    if getattr(sys, 'frozen', False):
        # ===== EXECUTÁVEL COMPILADO COM PYINSTALLER =====
        application_path = sys._MEIPASS
        tesseract_exe = os.path.join(application_path, 'ocr', 'tesseract.exe')
        tessdata_path = os.path.join(application_path, 'ocr', 'tessdata')
        
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe
        os.environ['TESSDATA_PREFIX'] = tessdata_path
        
    else:
        # ===== SCRIPT PYTHON NORMAL =====
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tesseract_exe = os.path.join(script_dir, 'ocr', 'tesseract.exe')
        tessdata_path = os.path.join(script_dir, 'ocr', 'tessdata')
        
        if os.path.exists(tesseract_exe):
            pytesseract.pytesseract.tesseract_cmd = tesseract_exe
            os.environ['TESSDATA_PREFIX'] = tessdata_path

# Configura o Tesseract ao importar o módulo
configure_tesseract()

# ============================================================================
# DADOS DOS MAPAS DO OVERWATCH 2
# ============================================================================

# Lista de mapas em inglês (referência principal)
MAPS = [
    # Control
    "Antarctic Peninsula",
    "Busan",
    "Ilios",
    "Lijiang Tower",
    "Nepal",
    "Oasis",
    "Samoa",
    # Escort
    "Circuit Royal",
    "Dorado",
    "Havana",
    "Junkertown",
    "Rialto",
    "Route 66",
    "Shambali Monastery",
    "Watchpoint: Gibraltar",
    # Hybrid
    "Blizzard World",
    "Eichenwalde",
    "Hollywood",
    "King's Row",
    "Midtown",
    "Numbani",
    "Paraíso",
    # Push
    "Colosseo",
    "Esperança",
    "New Queen Street",
    "Runasapi",
    # Flashpoint
    "Aatlis",
    "New Junk City",
    "Suravasa"
]

# Traduções PT-BR para inglês
TRANSLATIONS = {
    # Traduções portuguesas
    "Nova Queen Street": "New Queen Street",
    "Torre Lijiang": "Lijiang Tower",
    "Monastério de Shambali": "Shambali Monastery",
    "Monastério Shambali": "Shambali Monastery",
    "Observatório: Gibraltar": "Watchpoint: Gibraltar",
    "Observatório Gibraltar": "Watchpoint: Gibraltar",
    "Observatorio: Gibraltar": "Watchpoint: Gibraltar",  # Sem acento
    "Observatorio Gibraltar": "Watchpoint: Gibraltar",   # Sem acento
    "Rota 66": "Route 66",
    "Nova Junk City": "New Junk City",
    # Variações sem acento
    "Paraiso": "Paraíso",
    "Esperanca": "Esperança",
}

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def clean_text_line(line):
    """
    Limpa uma linha de texto removendo prefixos e caracteres extras.
    Remove coisas como "VO |", ">>", etc.
    
    Args:
        line (str): Linha original
        
    Returns:
        str: Linha limpa
    """
    # Remove prefixos comuns
    line = re.sub(r'^(VO\s*\||\|\s*|>+|\-+|=+)\s*', '', line, flags=re.IGNORECASE)
    
    # Remove espaços extras
    line = ' '.join(line.split())
    
    return line.strip()


def extract_map_candidates(text):
    """
    Extrai possíveis nomes de mapas do texto, incluindo substrings.
    
    Args:
        text (str): Texto completo extraído
        
    Returns:
        list: Lista de candidatos a nomes de mapas
    """
    candidates = []
    
    # Divide em linhas
    lines = text.split('\n')
    
    for line in lines:
        if not line.strip():
            continue
        
        # Limpa a linha
        cleaned = clean_text_line(line)
        if cleaned:
            candidates.append(cleaned)
        
        # Também adiciona a linha original para matching
        if line.strip() and line.strip() != cleaned:
            candidates.append(line.strip())
        
        # Tenta extrair substrings após separadores comuns
        for separator in ['|', '>', '-', ':']:
            if separator in line:
                parts = line.split(separator)
                for part in parts:
                    part = part.strip()
                    if len(part) > 3:  # Ignora partes muito curtas
                        candidates.append(part)
    
    return candidates

# ============================================================================
# FUNÇÕES PRINCIPAIS
# ============================================================================

def normalize_text(text):
    """
    Normaliza o texto removendo acentos, caracteres especiais
    e convertendo espaços em hífens.
    
    Args:
        text (str): Texto original
        
    Returns:
        str: Texto normalizado
    """
    if not text:
        return ""
    
    # Remove acentos
    text = unidecode(text)
    # Remove aspas simples
    text = text.replace("'", "")
    # Remove dois pontos
    text = text.replace(":", "")
    # Substitui ç por c (garantindo, mesmo que unidecode já faça)
    text = text.replace("ç", "c").replace("Ç", "C")
    # Substitui espaços por hífens
    text = text.replace(" ", "-")

    text = text.lower()
    
    return text


def extract_text_from_image(image_path):
    """
    Extrai texto de uma imagem usando OCR do Tesseract.
    
    Args:
        image_path (str): Caminho para a imagem
        
    Returns:
        str: Texto extraído ou string vazia em caso de erro
    """
    try:
        # Abre a imagem
        img = Image.open(image_path)
        
        # Configuração do Tesseract para melhor precisão
        custom_config = r'--oem 3 --psm 6'
        
        # Tenta extrair texto em português
        try:
            text_pt = pytesseract.image_to_string(img, lang='por', config=custom_config)
        except Exception:
            text_pt = ""
        
        # Tenta extrair texto em inglês
        try:
            text_en = pytesseract.image_to_string(img, lang='eng', config=custom_config)
        except Exception:
            text_en = ""
        
        # Combina ambos os textos para análise
        combined_text = text_pt + "\n" + text_en
        
        return combined_text.strip()
        
    except Exception as e:
        print(f"[ERRO] Falha ao extrair texto da imagem: {e}")
        return ""


def find_best_match(extracted_text):
    """
    Encontra o melhor match de mapa no texto extraído usando fuzzy matching.
    Procura em todo o texto, incluindo substrings.
    
    Args:
        extracted_text (str): Texto extraído do OCR
        
    Returns:
        tuple: (nome_do_mapa, confianca) ou (None, 0) se não encontrado
    """
    if not extracted_text:
        return None, 0
    
    # Lista completa para matching (inglês + traduções)
    all_map_names = MAPS.copy()
    all_map_names.extend(TRANSLATIONS.keys())
    
    # Cria versões lowercase para matching case-insensitive
    map_names_lower = [name.lower() for name in all_map_names]
    map_names_dict = {name.lower(): name for name in all_map_names}
    
    # Extrai todos os candidatos possíveis do texto
    candidates = extract_map_candidates(extracted_text)
    
    best_match = None
    best_score = 0
    
    # Para cada candidato extraído
    for candidate in candidates:
        if not candidate:
            continue
        
        # Converte candidato para lowercase
        candidate_lower = candidate.lower()
        
        # Busca o melhor match usando fuzzy matching (case-insensitive)
        result = process.extractOne(
            candidate_lower,
            map_names_lower,
            scorer=fuzz.ratio,
            score_cutoff=55  # Reduzido para 55% para pegar mais matches
        )
        
        if result and result[1] > best_score:
            # Recupera o nome original do mapa
            best_match = map_names_dict[result[0]]
            best_score = result[1]
    
    # Se não encontrou com ratio, tenta partial_ratio (substring matching)
    if best_score < 70:  # Se não tem confiança alta, tenta partial
        for candidate in candidates:
            if not candidate:
                continue
            
            candidate_lower = candidate.lower()
            
            result = process.extractOne(
                candidate_lower,
                map_names_lower,
                scorer=fuzz.partial_ratio,
                score_cutoff=70  # Partial ratio precisa ser mais alto
            )
            
            if result and result[1] > best_score:
                best_match = map_names_dict[result[0]]
                best_score = result[1]
    
    # Se encontrou um match
    if best_match:
        # Se for uma tradução, converte para inglês
        if best_match in TRANSLATIONS:
            return TRANSLATIONS[best_match], best_score
        else:
            return best_match, best_score
    
    return None, 0


def save_map_name(map_name, output_path="map.txt"):
    """
    Salva o nome do mapa normalizado em um arquivo.
    
    Args:
        map_name (str): Nome do mapa em inglês
        output_path (str): Caminho do arquivo de saída
        
    Returns:
        str: Nome normalizado que foi salvo, ou None se erro
    """
    try:
        # Normaliza o nome do mapa
        normalized_name = normalize_text(map_name)
        
        # Salva no arquivo
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(normalized_name)
        
        print(f"Mapa detectado: {map_name}")
        #print(f"✓ Salvo como: {normalized_name}")
        
        return normalized_name
        
    except Exception as e:
        print(f"[ERRO] Falha ao salvar arquivo: {e}")
        return None


def executar():
    """
    Função principal que será chamada pela main.py
    Extrai o mapa da screenshot e salva em map.txt
    
    Returns:
        bool: True se sucesso, False se falhou
    """
    # Define os caminhos
    image_path = os.path.join("print", "map", "map.png")
    output_path = "map.txt"
    
    # Verifica se a imagem existe
    if not os.path.exists(image_path):
        print(f"[ERRO] Imagem não encontrada em '{image_path}'")
        return False
    
    # Extrai texto da imagem
    extracted_text = extract_text_from_image(image_path)
    
    if not extracted_text:
        print("[ERRO] Não foi possível extrair texto da imagem")
        return False
    
    # Mostra o texto extraído
    #print(f"Texto extraído da imagem:")
    #print("-" * 50)
    #print(extracted_text)
    #print("-" * 50)
    #print()
    
    # Encontra o melhor match
    map_name, confidence = find_best_match(extracted_text)
    
    if not map_name:
        print("[ERRO] Nenhum mapa reconhecido no texto extraído")
        return False
    
    print(f"Confiança: {confidence}%")
    print()
    
    # Salva o resultado
    normalized = save_map_name(map_name, output_path)
    
    if normalized:
        return True
    else:
        return False


def main():
    """
    Função main para execução standalone
    """
    try:
        success = executar()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[ERRO] Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()