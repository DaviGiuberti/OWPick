from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import sys
import os

def executar():
    # --- CONFIGURAÇÕES ---
    MAPS = [
        # Control
        "antarctic-peninsula", "busan", "ilios", "lijiang-tower", "nepal", "oasis", "samoa",
        # Escort
        "circuit-royal", "dorado", "havana", "junkertown", "rialto", "route-66", "shambali-monastery", "watchpoint-gibraltar",
        # Hybrid
        "blizzard-world", "eichenwalde", "hollywood", "kings-row", "midtown", "numbani", "paraiso",
        # Push
        "colosseo", "esperanca", "new-queen-street", "runasapi",
        # Flashpoint
        "aatlis", "new-junk-city", "suravasa",
    ]
    
    TIERS = ["Master", "Grandmaster"]
    OUTDIR = "winratemaps"
    os.makedirs(OUTDIR, exist_ok=True)

    # Configurações do Chrome (headless)
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--log-level=3") # Remove logs desnecessários do console do Chrome
    
    # Inicializa o driver
    driver = webdriver.Chrome(options=chrome_options)

    # Variáveis para a barra de progresso
    total_steps = len(MAPS) * len(TIERS)
    current_step = 0
    bar_length = 30  # Tamanho visual da barra

    print("\nIniciando download dos dados...\n")

    try:
        for map_name in MAPS:
            for tier in TIERS:
                current_step += 1
                
                # Nome do arquivo
                filename = f"{map_name}_{tier}.html"
                filepath = os.path.join(OUTDIR, filename)
                
                # Monta a URL
                url = (
                    "https://overwatch.blizzard.com/en-us/rates/"
                    f"?input=PC&map={map_name}&region=Americas&role=All&rq=1&tier={tier}"
                )

                # --- LÓGICA DA BARRA DE CARREGAMENTO ---
                # Calcula porcentagem
                percent = 100 * (current_step / float(total_steps))
                # Calcula quantos "blocos" preencher
                filled_length = int(bar_length * current_step // total_steps)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                
                # Texto a ser exibido (com padding de espaços no final para limpar textos longos anteriores)
                status_msg = f"\rCarregando: |{bar}| {percent:.1f}% - Baixando: {map_name} [{tier}]"
                # Preenche com espaços vazios para garantir que limpe a linha anterior se o nome do mapa encurtar
                sys.stdout.write(status_msg.ljust(100)) 
                sys.stdout.flush()
                # ---------------------------------------

                try:
                    driver.get(url)
                    # Tempo de espera (pode ajustar conforme sua conexão)
                    time.sleep(3)
                    
                    html_completo = driver.page_source
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html_completo)
                        
                except Exception as e:
                    # Se der erro, pulamos uma linha para não estragar a barra e mostramos o erro
                    sys.stdout.write(f"\nErro no mapa \"{map_name}\" Tier \"{tier}\"\n")
                    sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário.")
    finally:
        driver.quit()
        # Finaliza com uma nova linha limpa e mensagem de conclusão
        sys.stdout.write(f"\n\nProcesso finalizado! Arquivos salvos em: {OUTDIR}\n")

if __name__ == "__main__":
    executar()