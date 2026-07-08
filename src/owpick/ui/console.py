"""console.py — Orquestrador de console: menu, hotkeys e threads (camada ui).

Chama os casos de uso de owpick.pipeline e delega a apresentação do ranking a
owpick.ui.ranking_view. É a única camada que imprime o fluxo ao usuário.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import keyboard

from owpick import log as applog
from owpick import paths, pipeline, settings
from owpick.i18n import t
from owpick.infra import resources, stats_update, storage, updater, validation
from owpick.log import get_logger, setup_logging
from owpick.ui import favorites, hotkey, profiles, ranking_view, roles, sim, weights

log = get_logger("console")

IN_MAIN = True  # Não executa o pipeline (TAB+1) quando fora do menu principal


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------
def print_main_menu():
    print(t("menu.main"))


def print_small_menu():
    print(t("menu.small"))


# ---------------------------------------------------------------------------
# Casos de uso acionados pelo usuário
# ---------------------------------------------------------------------------
def run_pipeline():
    """Fluxo TAB+1: captura → matching → mapa → ranking (tudo em memória)."""
    try:
        t0 = time.perf_counter()
        # Spinner do rich durante o pipeline (tarefa 6.5): usa o MESMO console
        # da ranking_view para que as mensagens de progresso convivam com o
        # status sem quebrar a renderização.
        with ranking_view.console.status("Analisando a tela..."):
            result = pipeline.run_pipeline(
                report=lambda msg: ranking_view.console.print(f">>> {msg}"),
                # Lido do módulo (não importado por valor): setup_logging só
                # define DEBUG_MODE depois que console.py já foi importado.
                save_debug=applog.DEBUG_MODE,
            )
        if result is None:
            return
        # "O que houve + o que fazer": nenhum herói identificado = quase
        # certamente a captura não pegou a tela de seleção do Overwatch.
        if not result.allies and not result.enemies:
            combo = hotkey.combo_label(current_combo())
            print(f"\n{t('pipeline.no_heroes_detected', hotkey=combo)}")
        print(f"\n>>> {t('pipeline.choosing')}")
        ranking_view.render(result)
        log.debug("pipeline completo: %.2fs", time.perf_counter() - t0)
    except Exception as e:
        log.error("erro no pipeline", exc_info=True)
        print(t("pipeline.error", error=e))
        import traceback

        traceback.print_exc()
    finally:
        print_small_menu()


def run_role():
    try:
        print("\n>>> Qual a Role que está jogando?")
        roles.executar()
        print("Role atualizada.")
    except Exception as e:
        print(f"Erro em roles: {e}")


def run_favorite():
    try:
        print("\n>>> Quais heróis quer adicionar ao sistema de pontuação?")
        favorites.executar()
    except Exception as e:
        print(f"Erro em favoritos: {e}")


def run_update_stats():
    """Atualiza o stats_inputs.csv local rodando o scraper (tarefa 5.3)."""
    try:
        print("\n>>> Atualizando stats de meta...")
        stats_update.update_stats(report=print)
    except Exception as e:
        print(f"Erro ao atualizar stats: {e}")


def run_profiles():
    """Menu de múltiplos perfis (tarefa 6.8)."""
    try:
        print("\n>>> Perfis (role + favoritos + preset + tier)")
        profiles.executar()
    except Exception as e:
        print(f"Erro em perfis: {e}")


def run_weights_config():
    """Troca o preset de pesos do modelo (vinculado ao perfil ativo)."""
    try:
        print("\n>>> Preset de pesos do modelo")
        weights.executar()
    except Exception as e:
        print(f"Erro ao alterar o preset de pesos: {e}")


def run_sim(args: str):
    """Modo manual/simulação (tarefa 6.7): scoring sem captura."""
    try:
        sim.executar(args)
    except Exception as e:
        log.error("erro na simulação", exc_info=True)
        print(f"Erro na simulação: {e}")


def run_hotkey_config():
    """Configura a hotkey de captura e re-registra o hook com a nova combinação."""
    try:
        print("\n>>> Configurar a hotkey de captura")
        changed = hotkey.executar()
        if changed is not None:
            disable_pipeline_hotkey_hook()
            enable_pipeline_hotkey_hook()
    except Exception as e:
        print(f"Erro na configuração de hotkey: {e}")


def _notify_update_available(update: dict):
    """Aviso NÃO bloqueante de update disponível (callback da thread de fundo).

    Renderizado como um painel rich destacado (borda + cor) para não passar
    despercebido no meio da saída do console.
    """
    from rich.panel import Panel
    from rich.text import Text

    msg = Text(t("update.available", version=update.get("version", "?")), style="bold yellow")
    ranking_view.console.print()
    ranking_view.console.print(
        Panel(
            msg,
            title=f"[bold black on yellow] {t('update.badge')} [/]",
            border_style="yellow",
            expand=False,
        )
    )


def run_apply_update():
    """Aplica a atualização pendente (comando 'update' — tarefa 7.2)."""
    if updater.pending_update is None:
        print(f"\n>>> {t('update.none')}")
        return
    print(f"\n>>> {t('update.applying')}")
    updater.apply_pending_update()  # encerra o processo se a aplicação seguir


def run_toggle_explain():
    """Liga/desliga a explicação do ranking (persistido no settings — tarefa 6.4)."""
    try:
        cfg = settings.get()
        cfg.explain_ranking = not cfg.explain_ranking
        settings.save(cfg)
        estado = "ATIVADA" if cfg.explain_ranking else "DESATIVADA"
        print(f"\n>>> Explicação do ranking {estado}.")
    except Exception as e:
        print(f"Erro ao alternar a explicação do ranking: {e}")


# Função para não travar o teclado nem o input enquanto outro comando roda.
def spawn_in_thread(func, *args, **kwargs):
    t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Hotkey global de captura (configurável — tarefa 6.2; padrão TAB+1)
# ---------------------------------------------------------------------------
_detector: hotkey.HotkeyDetector | None = None  # hook manual (combos com TAB)
_hotkey_handle = None  # handle do keyboard.add_hotkey (combos padrão)
_last_trigger = 0.0  # anti-spam: 1 disparo por segundo


def current_combo() -> list[str]:
    """Combinação de captura ativa (settings.json; padrão TAB+1)."""
    combo = [k.lower() for k in settings.get().hotkey if k]
    return combo or list(hotkey.DEFAULT_COMBO)


def _trigger_pipeline():
    """Dispara o pipeline (com gating do menu principal e cooldown anti-spam)."""
    global _last_trigger
    if not IN_MAIN:
        return
    now = time.monotonic()
    if now - _last_trigger < 1.0:  # substitui o antigo unhook/rehook de 0.2s
        return
    _last_trigger = now
    print(f"Detectado {hotkey.combo_label(current_combo())} -> executando pipeline.")
    spawn_in_thread(run_pipeline)


def _on_key_event(event):  # chamada para TODA tecla (só no modo hook manual)
    if _detector is not None:
        _detector.handle(event.event_type, event.name)


def enable_pipeline_hotkey_hook():
    """
    Registra a hotkey de captura: combinações padrão usam keyboard.add_hotkey;
    combinações com TAB (o modificador que o Win32 não suporta) usam o hook
    manual + HotkeyDetector (mesma mecânica do antigo TAB+1).
    """
    global _detector, _hotkey_handle
    combo = current_combo()
    try:
        if "tab" in combo:
            _detector = hotkey.HotkeyDetector(combo, _trigger_pipeline)
            keyboard.hook(_on_key_event)
        else:
            _hotkey_handle = keyboard.add_hotkey("+".join(combo), _trigger_pipeline)
    except Exception as e:
        print(f"[hotkey-hook] Erro ao ativar hook: {e}")


def disable_pipeline_hotkey_hook():
    global _detector, _hotkey_handle
    try:
        if _detector is not None:
            _detector = None
            keyboard.unhook(_on_key_event)
        if _hotkey_handle is not None:
            keyboard.remove_hotkey(_hotkey_handle)
            _hotkey_handle = None
    except Exception as e:
        print(f"[hotkey-hook] Erro ao desativar hook: {e}")


# ---------------------------------------------------------------------------
# Controle de input
# ---------------------------------------------------------------------------
def call_and_pause_main(func, *args, **kwargs):
    """Pausa o TAB+1 enquanto um comando do menu roda."""
    global IN_MAIN
    IN_MAIN = False
    try:
        func(*args, **kwargs)
    finally:
        IN_MAIN = True
        print_small_menu()


def input_loop():
    print_main_menu()

    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nEntrada interrompida.")
            break

        if not cmd:
            continue

        if cmd == "2":
            call_and_pause_main(run_role)
        elif cmd == "3":
            call_and_pause_main(run_favorite)
        elif cmd == "4":
            call_and_pause_main(run_update_stats)
        elif cmd == "5":
            call_and_pause_main(run_hotkey_config)
        elif cmd == "6":
            call_and_pause_main(run_toggle_explain)
        elif cmd == "7":
            call_and_pause_main(run_profiles)
        elif cmd == "8":
            call_and_pause_main(run_weights_config)
        elif cmd == "update":
            call_and_pause_main(run_apply_update)
        elif cmd.startswith("sim"):
            call_and_pause_main(run_sim, cmd[3:].strip())
        elif cmd in ("exit", "quit"):
            print("Encerrando programa...")
            disable_pipeline_hotkey_hook()
            try:
                keyboard.clear_all_hotkeys()
            except Exception:
                pass
            # Se há update pendente e não foi aplicado por comando, aplica ao
            # fechar (tarefa 7.2). apply_pending_update encerra o processo.
            if updater.pending_update is not None:
                print(f">>> {t('update.applying')}")
                updater.apply_pending_update()
            os._exit(0)
        else:
            print(t("menu.unknown_command"))
            print_small_menu()


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def main():
    global IN_MAIN

    # Identidade do app na taskbar do Windows (AppUserModelID + ícone da
    # janela). Precisa rodar antes de qualquer print/janela.
    resources.configure_windows_app_identity()

    # Estrutura de diretórios de dados do usuário / cache e migração automática
    # dos dados de versões antigas (que gravavam ao lado do exe / no CWD).
    paths.ensure_dirs()
    migrated = paths.migrate_legacy_user_data()

    # Update seguro (tarefa 7.1): se chegamos até aqui, a versão instalada subiu
    # com sucesso — apaga o backup 'OWPick.old' deixado pelo último update.
    updater.cleanup_old_backup()

    # Settings do usuário (settings.json em %APPDATA%\OWPick — tarefa 6.1).
    # Carregado cedo: o modo debug pode vir da flag --debug OU do settings.
    cfg = settings.get()
    debug = "--debug" in sys.argv or cfg.debug

    # Logging: arquivo rotativo em %APPDATA%\OWPick\logs (DEBUG) + console
    # limpo (INFO; --debug sobe o console para DEBUG).
    setup_logging(debug=debug)
    if migrated:
        log.info(
            "dados do usuário migrados para %s: %s", paths.user_data_dir(), ", ".join(migrated)
        )
    log.debug(
        "OWPick v%s iniciado (frozen=%s)",
        updater.get_local_version(),
        getattr(sys, "frozen", False),
    )

    # Validação dos dados (matrizes/stats/templates) — só no modo --debug, com
    # aviso claro do que estiver faltando/errado (tarefa 5.2). No modo normal o
    # boot não paga esse custo; a rede de testes já cobre os dados versionados.
    if debug:
        validation.report_problems(validation.validate_all())

    # Verificação de atualização NÃO BLOQUEANTE (tarefa 7.2): o boot segue
    # imediatamente; a checagem roda em thread de fundo e, se houver versão
    # nova, avisa sem travar (linha no console + comando 'update').
    updater.start_background_check(on_available=_notify_update_available)

    if not os.path.exists(storage.role_path()):
        run_role()
    if not os.path.exists(storage.favorites_path()):
        run_favorite()

    IN_MAIN = True
    enable_pipeline_hotkey_hook()  # registra a hotkey de captura (padrão TAB+1)
    input_thread = threading.Thread(target=input_loop, daemon=True)
    input_thread.start()

    combo_label = hotkey.combo_label(current_combo())
    print("=" * 50)
    print(t("boot.started"))
    print(t("boot.hotkey_hint", hotkey=combo_label))
    print(t("boot.menu_hint"))
    print("=" * 50)

    try:
        while True:
            time.sleep(1)
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


if __name__ == "__main__":
    main()
