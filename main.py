import keyboard
import time
import threading
import sys
import os
import msvcrt
import choose_ow_hero
import comparar
import favoriteHero
import roles
import screenshot


IN_MAIN = True # Não executa nada na main quando false

# Menus

def print_main_menu():
    print(
        "Comandos disponíveis:\n"
        "  2 -> alterar Role/Função\n"
        "  3 -> adicionar/remover heróis favoritos\n"
        "  4 -> (Teste)) adicionar/remover prioridade para os inimigos mais counters\n"
    )

def print_small_menu():
    print(
        "\n[2] Role  [3] Favoritos  [4] (Teste) Priorizar Counters\n"
    )


# Funções

def run_pipeline():
    """ Executa o fluxo principal: Print -> Comparar -> Escolher Herói """
    try:
        print(">>> Capturando a tela...")
        screenshot.executar()

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

def toggle_prioritize_file():
    filename = "prioritize.txt"

    # Leitura
    try:
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read().strip()
    except FileNotFoundError:
        content = None

    # Define novo valor
    if content == "0":
        new_content = "1"
        msg = "Prioridade para counters ativada"
    elif content is None:
        new_content = "1"
        msg = "Prioridade para counters ativada (arquivo criado)"
    else:
        new_content = "0"
        msg = "Prioridade para counters desativada"

    # Escrita
    try:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(new_content)
        print(msg)
    except Exception as e:
        print(f"Erro ao escrever no arquivo: {e}")

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
        elif cmd.endswith("3"):
            call_and_pause_main(run_favorite)
        elif cmd.endswith("4"):
            call_and_pause_main(toggle_prioritize_file)
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
        run_favorite()

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