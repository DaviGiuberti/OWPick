"""hotkey.py — Hotkey de captura configurável (camada ui, tarefa 6.2).

Dois papéis:

1. `HotkeyDetector` — detecção genérica de uma combinação arbitrária a partir
   do stream de eventos da lib `keyboard` (generaliza o antigo par
   `_tab_pressed`/`_on_key_event`, que era fixo em TAB+1). É usado pelo hook
   manual do console quando a combinação contém TAB (o `keyboard.add_hotkey`
   cobre as combinações padrão; TAB como modificador é o caso exótico — nota
   técnica: o RegisterHotKey do Win32 não aceita TAB, por isso a lib
   `keyboard` continua sendo a escolha).

2. UI de captura (`executar`) — o usuário pressiona a combinação desejada, ela
   aparece na tela em tempo real e ele confirma a nova combinação ou volta ao
   padrão (TAB+1). Persistida em settings.json (tarefa 6.1).

Como todos os menus da ui, as fontes de entrada são INJETÁVEIS (`ask`,
`read_event`) com default real (`input`/`keyboard.read_event`) — em produção o
comportamento não muda; os testes passam stubs (é a "forma de testar que a
captura de hotkey funciona" pedida pelo autor).
"""

from __future__ import annotations

from collections.abc import Callable

from owpick import settings
from owpick.log import get_logger

log = get_logger("hotkey")

DEFAULT_COMBO: list[str] = list(settings.DEFAULT_HOTKEY)  # ["tab", "1"]


def combo_label(combo: list[str]) -> str:
    """Rótulo legível da combinação: ["tab","1"] -> "TAB+1"."""
    return "+".join(k.upper() for k in combo)


# ---------------------------------------------------------------------------
# Detecção (hook manual) — generalização do antigo _tab_pressed/_on_key_event
# ---------------------------------------------------------------------------
class HotkeyDetector:
    """
    Detecta uma combinação arbitrária num stream de eventos down/up.

    A ÚLTIMA tecla da combinação é a de disparo; as demais precisam estar
    seguradas quando ela desce (mesma semântica do antigo TAB+1: TAB seguro,
    "1" dispara). `handle` devolve True quando a combinação disparou.
    """

    def __init__(self, combo: list[str], on_trigger: Callable[[], None]) -> None:
        self.combo = [k.lower() for k in combo]
        self.trigger_key = self.combo[-1]
        self.modifiers = self.combo[:-1]
        self.on_trigger = on_trigger
        self._pressed: set[str] = set()

    def handle(self, event_type: str, name: str | None) -> bool:
        if not name:
            return False
        name = name.lower()
        if event_type == "down":
            if name == self.trigger_key:
                if all(m in self._pressed for m in self.modifiers):
                    self.on_trigger()
                    return True
                return False
            self._pressed.add(name)
        else:
            self._pressed.discard(name)
        return False


# ---------------------------------------------------------------------------
# Captura interativa da nova combinação (tempo real)
# ---------------------------------------------------------------------------
def _default_read_event():
    import keyboard

    return keyboard.read_event()


def capture_combo(
    read_event: Callable[[], object] = _default_read_event,
    echo: Callable[[str], None] = print,
) -> list[str]:
    """
    Lê a combinação do usuário: cada tecla pressionada entra na combinação e é
    exibida em tempo real; soltar TODAS as teclas finaliza a captura.
    """
    echo("Pressione a combinação desejada (solte todas as teclas para finalizar)...")
    order: list[str] = []  # teclas na ordem em que desceram (a última dispara)
    held: set[str] = set()
    while True:
        ev = read_event()
        name = (getattr(ev, "name", None) or "").lower()
        event_type = getattr(ev, "event_type", "")
        if not name:
            continue
        if event_type == "down":
            if name not in held:
                held.add(name)
                if name not in order:
                    order.append(name)
                    echo(f"  > {combo_label(order)}")  # feedback em tempo real
        elif name in held:
            held.discard(name)
            if not held:
                return order


def validate_combo(combo: list[str]) -> str | None:
    """Validação básica de conflito. None = ok; senão a mensagem do problema."""
    if not combo:
        return "Nenhuma tecla capturada."
    if len(combo) == 1 and len(combo[0]) == 1:
        # Uma única tecla de digitação dispararia o pipeline ao digitar no menu.
        return (
            f"'{combo_label(combo)}' é uma tecla comum de digitação — "
            "use uma combinação (ex.: CTRL+F9) para evitar disparos acidentais."
        )
    return None


# ---------------------------------------------------------------------------
# Menu de configuração
# ---------------------------------------------------------------------------
def executar(
    ask: Callable[[str], str] = input,
    read_event: Callable[[], object] = _default_read_event,
) -> list[str] | None:
    """
    Menu da hotkey: captura uma nova combinação (com confirmação) ou volta ao
    padrão. Retorna a combinação persistida, ou None se nada mudou.
    """
    cfg = settings.get()
    print(f"Hotkey de captura atual: {combo_label(cfg.hotkey)}")
    print("  1 - Capturar nova combinação")
    print(f"  2 - Voltar ao padrão ({combo_label(DEFAULT_COMBO)})")
    print("  3 - Cancelar")
    choice = ask("\n> ").strip()

    if choice == "1":
        combo = capture_combo(read_event)
        problem = validate_combo(combo)
        if problem:
            print(f"✗ Combinação rejeitada: {problem}")
            return None
        print(f"Combinação capturada: {combo_label(combo)}")
        confirm = ask("Confirmar nova hotkey? (s/n) ").strip().lower()
        if confirm not in ("s", "sim", "y", "yes"):
            print("Combinação descartada — hotkey mantida.")
            return None
        cfg.hotkey = combo
        settings.save(cfg)
        print(f"✓ Hotkey atualizada para {combo_label(combo)}")
        return combo

    if choice == "2":
        cfg.hotkey = list(DEFAULT_COMBO)
        settings.save(cfg)
        print(f"✓ Hotkey restaurada para o padrão ({combo_label(DEFAULT_COMBO)})")
        return list(DEFAULT_COMBO)

    print("Configuração de hotkey cancelada.")
    return None
