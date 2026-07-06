"""weights.py — Menu de escolha do preset de pesos do modelo (camada ui).

Deixa o usuário trocar o preset (Equilibrado / Counter-first / Meta-first /
Conforto+) direto do menu. A troca é VINCULADA ao perfil ativo (se houver) via
profiles.set_weights_preset — assim a escolha acompanha o perfil.

Como os demais menus da ui, a entrada é INJETÁVEL (`ask`, default input()).
"""

from __future__ import annotations

from collections.abc import Callable

from owpick import settings
from owpick.core.scoring import PRESET_LABELS, PRESETS
from owpick.ui import profiles

# Ordem estável de exibição (mesma ordem de PRESETS).
_ORDER = list(PRESETS)


def _describe(name: str) -> str:
    return PRESET_LABELS.get(name, name)


def executar(ask: Callable[[str], str] = input) -> str | None:
    """
    Mostra o preset atual, lista as opções e aplica a escolha (vinculando ao
    perfil ativo). Retorna o preset escolhido, ou None se nada mudou.
    """
    cfg = settings.get()
    active_profile = cfg.active_profile

    print(f"\nPreset de pesos atual: {_describe(cfg.weights_preset)}")
    if active_profile:
        print(f"(vinculado ao perfil ativo: '{active_profile}')")
    print("\nEscolha um preset:")
    for i, name in enumerate(_ORDER, start=1):
        marker = " <- atual" if name == cfg.weights_preset else ""
        print(f"  {i} - {_describe(name)}{marker}")
    print(f"  {len(_ORDER) + 1} - Cancelar")

    choice = ask("\nOpção: ").strip()
    if not choice.isdigit():
        print("✗ Opção inválida")
        return None

    idx = int(choice)
    if idx == len(_ORDER) + 1:
        print("Escolha de preset cancelada.")
        return None
    if not 1 <= idx <= len(_ORDER):
        print("✗ Opção inválida")
        return None

    name = _ORDER[idx - 1]
    profiles.set_weights_preset(name)
    msg = f"✓ Preset alterado para {_describe(name)}"
    if active_profile:
        msg += f" (vinculado ao perfil '{active_profile}')"
    print(msg)
    return name
