import os
import sys
import time
import platform
import subprocess
import contextlib

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

@contextlib.contextmanager
def suppress_stderr():
    """
    Redireciona temporariamente o STDERR do processo para os.devnull.
    Usado para suprimir mensagens do Chrome/Chromedriver que são escritas em stderr.
    """
    devnull = os.open(os.devnull, os.O_RDWR)
    saved_stderr = os.dup(2)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        # restaura stderr
        os.dup2(saved_stderr, 2)
        os.close(devnull)
        os.close(saved_stderr)

def print_progress(current, total, bar_length=40):
    percent = current / total if total else 1
    filled = int(bar_length * percent)
    bar = "█" * filled + "-" * (bar_length - filled)
    sys.stdout.write(f"\rCarregando: |{bar}| {current}/{total} ({percent*100:3.0f}%)")
    sys.stdout.flush()

def executar():
    MAPS = [
        # Control
        "antarctic-peninsula","busan","ilios","lijiang-tower","nepal","oasis","samoa",
        # Escort
        "circuit-royal","dorado","havana","junkertown","rialto","route-66","shambali-monastery","watchpoint-gibraltar",
        # Hybrid
        "blizzard-world","eichenwalde","hollywood","kings-row","midtown","numbani","paraiso",
        # Push
        "colosseo","esperanca","new-queen-street","runasapi",
        # Flashpoint
        "aatlis","new-junk-city","suravasa",
    ]
    TIERS = ["Master", "Grandmaster"]
    OUTDIR = "winratemaps"
    os.makedirs(OUTDIR, exist_ok=True)

    # opções do Chrome para reduzir logs
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")       # headless moderno (se disponível)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    # tenta suprimir mensagens internas
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])

    # prepara service do chromedriver direcionando logs para NUL
    service = Service(log_path=os.devnull)

    # no Windows, tenta suprimir janela do processo chromedriver
    if platform.system() == "Windows":
        try:
            service.creationflags = subprocess.CREATE_NO_WINDOW
        except Exception:
            # se a versão de selenium não suportar, não é crítico
            pass

    total_tasks = len(MAPS) * len(TIERS)
    completed = 0
    errors = []

    # Suprimimos STDERR durante toda a vida do driver (início, requisições, etc.)
    # Assim 'DevTools listening' e os ERROR:... são geralmente suprimidos.
    with suppress_stderr():
        driver = webdriver.Chrome(service=service, options=chrome_options)
        try:
            # desenha barra inicial
            print_progress(completed, total_tasks)

            for map_name in MAPS:
                for tier in TIERS:
                    filename = f"{map_name}_{tier}.html"
                    filepath = os.path.join(OUTDIR, filename)

                    url = (
                        "https://overwatch.blizzard.com/en-us/rates/"
                        f"?input=PC&map={map_name}&region=Americas&role=All&rq=1&tier={tier}"
                    )
                    try:
                        # não imprimimos URL nem nome do mapa
                        driver.get(url)
                        time.sleep(3)
                        html_completo = driver.page_source
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(html_completo)
                    except Exception:
                        completed += 1
                        # antes de imprimir a mensagem curta, posiciona cursor
                        sys.stdout.write("\r")
                        sys.stdout.flush()
                        # esta mensagem aparece em stdout (visível), não em stderr
                        print(f'Houve um erro no mapa "{map_name}" Tier "{tier}". Por favor baixe novamente.')
                        print_progress(completed, total_tasks)
                        errors.append((map_name, tier))
                        continue

                    completed += 1
                    print_progress(completed, total_tasks)

            sys.stdout.write("\n")
            print("Processo finalizado.")

        finally:
            try:
                driver.quit()
            except Exception:
                pass

    # opcional: grava arquivo com erros se houver
    if errors:
        with open("errors.txt", "w", encoding="utf-8") as ef:
            for m, t in errors:
                ef.write(f"{m},{t}\n")

if __name__ == "__main__":
    executar()
