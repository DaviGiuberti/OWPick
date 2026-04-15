import keyboard
import time
import threading
import sys
import os
import msvcrt
import choose_ow_hero
import comparar
import compararMapa
import favoriteHero
import map as map_script
import retirarWinrate
import roles
import screenshot
import site_scrapper


MAP_FILE = "map.txt"
WINRATE_FILE = "winrate.xlsx"


IN_MAIN = True # Não executa nada na main quando false
WITH_MAP = True

# Menus

def print_main_menu():
    print(
        "Comandos disponíveis:\n"
        "  2 -> alterar Role/Função\n"
        "  3 -> adicionar/remover heróis favoritos\n"
        "  4 -> atualizar winrate dos mapas\n"
        "  5 -> remover pontos dos mapas no TAB+1\n"
    )

def print_small_menu():
    global WITH_MAP
    opcao_5 = "Sem Mapas na pontuação" if WITH_MAP else "Com Mapas na pontuação"
    
    print(
        f"\n[2] Role  [3] Favoritos  [4] Atualizar Winrate  [5] {opcao_5}"
    )


# Funções

def run_pipeline():
    """ Executa o fluxo principal: Print -> Comparar -> Escolher Herói """
    global WITH_MAP
    try:
        print(">>> Capturando a tela...")
        screenshot.executar()

        if WITH_MAP:
            # Executa o OCR para detectar o mapa
            success = compararMapa.executar()
            
            if success:
                # Se detectou o mapa com sucesso, tenta retirar a winrate
                try:
                    print("\n>>> Retirando a winrate do mapa detectado...")
                    retirarWinrate.executar()
                except Exception as e:
                    print(f"Aviso: Não foi possível obter winrate do mapa: {e}")
            else:
                print("\nFalha ao detectar o mapa. Tente novamente")

        print(">>> Comparando os prints com os heróis do Overwatch...")
        comparar.executar()

        print(">>> Executando escolha de herói...")
        choose_ow_hero.run_hero_ranking()

    except Exception as e:
        print(f"Erro no pipeline: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ao terminar, exibe o menu resumido (não altera estado IN_MAIN)
        print_small_menu()

def run_site():
    try:
        print(">>> Baixando a winrate de cada herói por mapa")
        site_scrapper.executar()
    except Exception as e:
        print(f"Erro no site_scrapper.py: {e}")

def run_map():
    try:
        map_script.executar()
    except Exception as e:
        print(f"Erro no mapa: {e}")
    try:
        print(">>> Retirando a winrate do mapa...")
        retirarWinrate.executar()
    except RuntimeError as e:
        print("")

def run_role():
    try:
        print(">>> Qual a Role que está jogando?")
        roles.executar()
        print("Role atualizada.")
    except Exception as e:
        print(f"Erro em roles: {e}")

def run_favorite():
    try:
        print(">>> Quais heróis quer adicionar ao sistema de pontuação?")
        favoriteHero.executar()
    except Exception as e:
        print(f"Erro em favoritos: {e}")

def remove_map():
    if os.path.exists(MAP_FILE) and os.path.exists(WINRATE_FILE):
        try:
            os.remove(MAP_FILE)
            os.remove(WINRATE_FILE)
            print("mapa removido com sucesso.")
        except Exception as e:
            print(f"Erro ao remover arquivo: {e}")
    else:
        print("Nenhum mapa encontrado para remover.")


# Função para não travar o teclado nem o input enquanto outro comando roda.
def spawn_in_thread(func, *args, **kwargs):
    t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t

# Hook-based hotkey (mais resiliente)

_tab_pressed = False # Diz se Tab está pressionado

def _on_key_event(event): # Essa função é chamada para TODA tecla pressionada ou solta.
    global _tab_pressed, IN_MAIN
    # event.event_type é 'down' ou 'up'
    name = event.name
    if name == 'tab': # Marca se TAB está pressionado.
        _tab_pressed = (event.event_type == 'down')
    elif name == '1' and event.event_type == 'down': # Detecta o 1.
        if _tab_pressed and IN_MAIN: # Só executa se TAB estiver pressionado e no menu principal
            try:
                keyboard.unhook(_on_key_event) # caso tenha spam de TAB+1
            except Exception:
                pass
            print("Detectado TAB+1 -> executando pipeline.")
            spawn_in_thread(run_pipeline)
            def rehook():
                time.sleep(0.2) # delay para reativar
                try:
                    keyboard.hook(_on_key_event) #reativa
                except Exception:
                    pass
            spawn_in_thread(rehook)

def enable_pipeline_hotkey_hook():
    try:
        keyboard.hook(_on_key_event)
    except Exception as e:
        print(f"[hotkey-hook] Erro ao ativar hook: {e}")

def disable_pipeline_hotkey_hook():
    try:
        keyboard.unhook(_on_key_event)
    except Exception as e:
        print(f"[hotkey-hook] Erro ao desativar hook: {e}")

# ---------- Controle de Input ----------

def call_and_pause_main(func, *args, **kwargs): 
    # Função que pausa a execução da main enquanto está em outro comando

    global IN_MAIN
    IN_MAIN = False # sinaliza que saímos do main
    try:
        func(*args, **kwargs)
    finally:
        # voltamos ao main
        IN_MAIN = True # assinala que voltamos para a main
        print_small_menu() # Volta menu

def input_loop():   # função em loop
    global WITH_MAP
    print_main_menu()

    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nEntrada interrompida.")
            break

        if not cmd:
            continue

        if cmd.endswith("2"):
            call_and_pause_main(run_role)
        #elif cmd.endswith("2"):
        #    call_and_pause_main(run_map)
        elif cmd.endswith("3"):
            call_and_pause_main(run_favorite)
        elif cmd.endswith("4"):
            print('Separando as winrates atualizadas de todos os mapas')
            call_and_pause_main(run_site)
        elif cmd.endswith("5"):
            if WITH_MAP:
                WITH_MAP = False
                remove_map()
            else:
                WITH_MAP = True
        #elif cmd.endswith("6"):
            # remover mapa é imediato, não precisa 'pausar' longa execução,
            # mas vamos mantê-lo sincronizado com o fluxo de pausa/remissão
            #all_and_pause_main(remove_map)
        elif cmd in ("exit", "quit"):
            print("Encerrando programa...")
            disable_pipeline_hotkey_hook()
            try:
                keyboard.clear_all_hotkeys()
            except Exception:
                pass
            os._exit(0)
        else:
            print("Comando não reconhecido.")
            print_small_menu()

# Configuração Inicial

if __name__ == "__main__":

    if not os.path.exists("Roles.txt"):
        run_role()
    if not os.path.exists("ALL.txt"):
        if not os.path.isdir("winratemaps"):
            print("\nApós escolher os personagens favoritos, o programa irá atualizar as winrates no site do Overwatch\n")
        run_favorite()
    if not os.path.isdir("winratemaps"):
        print('Baixando as winrates atualizadas de todos os mapas')
        run_site()

    # Inicialmente estamos no menu principal
    IN_MAIN = True
    enable_pipeline_hotkey_hook()  # registra TAB+1
    # Desta maneira o "TAB+1" e os comandos podem funcionar simultaneamente
    input_thread = threading.Thread(target=input_loop, daemon=True)
    input_thread.start()

    print("="*50)
    print(" PROGRAMA INICIADO - OWPick")
    print(" - Pressione TAB+1 (global) para executar o pipeline quando estiver no menu principal.")
    print(" - Use os números do menu e ENTER para rodar os outros comandos.")

    print("="*50)

    # Loop principal para manter o programa vivo
    try:
        while True:
            time.sleep(1)
            # se o thread de input morrer, encerramos
            if not input_thread.is_alive():
                break
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    finally:
        disable_pipeline_hotkey_hook()
        try:
            keyboard.clear_all_hotkeys()
        except Exception:
            pass
        print("Programa finalizado.")