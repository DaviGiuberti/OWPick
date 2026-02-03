from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import sys
import os

def executar():
    # lista de mapas
    MAPS = [
        # Control
        "antarctic-peninsula",
        "busan",
        "ilios",
        "lijiang-tower",
        "nepal",
        "oasis",
        "samoa",
        # Escort
        "circuit-royal",
        "dorado",
        "havana",
        "junkertown",
        "rialto",
        "route-66",
        "shambali-monastery",
        "watchpoint-gibraltar",
        # Hybrid
        "blizzard-world",
        "eichenwalde",
        "hollywood",
        "kings-row",
        "midtown",
        "numbani",
        "paraiso",
        # Push
        "colosseo",
        "esperanca",
        "new-queen-street",
        "runasapi",
        # Flashpoint
        "aatlis",
        "new-junk-city",
        "suravasa",
    ]
    
    TIERS = ["Master", "Grandmaster"]
    OUTDIR = "winratemaps"
    os.makedirs(OUTDIR, exist_ok=True)
    
    # Calcular total de downloads
    total_downloads = len(MAPS) * len(TIERS)
    current = 0
    
    # configurações do Chrome (headless)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")  # Reduzir logs do Chrome
    
    driver = webdriver.Chrome(options=chrome_options)
    
    erros = []
    
    try:
        for map_name in MAPS:
            for tier in TIERS:
                current += 1
                
                # Atualizar barra de progresso
                porcentagem = int((current / total_downloads) * 100)
                barra_tamanho = 50
                preenchido = int((current / total_downloads) * barra_tamanho)
                barra = "█" * preenchido + "░" * (barra_tamanho - preenchido)
                
                # Limpar linha anterior e mostrar progresso
                sys.stdout.write(f"\r[{barra}] {porcentagem}% ({current}/{total_downloads})")
                sys.stdout.flush()
                
                filename = f"{map_name}_{tier}.html"
                filepath = os.path.join(OUTDIR, filename)
                url = (
                    "https://overwatch.blizzard.com/en-us/rates/"
                    f"?input=PC&map={map_name}&region=Americas&role=All&rq=1&tier={tier}"
                )
                
                try:
                    driver.get(url)
                    time.sleep(3)
                    html_completo = driver.page_source
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html_completo)
                        
                except Exception as e:
                    erros.append(f"Erro no mapa '{map_name}' Tier '{tier}'")
        
        # Linha nova após completar
        print()
        
        # Mostrar erros se houver
        if erros:
            print("\n⚠️  Erros encontrados:")
            for erro in erros:
                print(f"  • {erro}")
            print("\nPor favor, execute o programa novamente para tentar baixar os mapas com erro.")
        else:
            print("✓ Download concluído com sucesso!")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    executar()