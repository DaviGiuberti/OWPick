"""profiles.py — Múltiplos perfis (camada ui, tarefa 6.8).

Cada perfil nomeado guarda: role + favoritos + preset de pesos + tier de stats
(settings.Profile, persistido em settings.json). Trocar de perfil APLICA os
valores pelos mecanismos existentes — Roles.txt (storage.write_role), arquivos
de favoritos (storage.save_heroes_to_files) e settings (weights_preset/
scraper_tier) — então o resto do app não precisa saber que perfis existem.

Como todos os menus da ui, a entrada é INJETÁVEL (`ask`, default input()).
"""

from __future__ import annotations

from collections.abc import Callable

from owpick import settings
from owpick.core.heroes import get_hero_role
from owpick.infra import storage
from owpick.log import get_logger

log = get_logger("profiles")


def snapshot_current() -> settings.Profile:
    """Fotografa o estado atual (role/favoritos/preset/tier) num Profile."""
    cfg = settings.get()
    return settings.Profile(
        role=storage.read_role(),
        favorites=storage.load_favorites(),
        weights_preset=cfg.weights_preset,
        scraper_tier=cfg.scraper_tier,
    )


def save_profile(name: str) -> settings.Profile:
    """Salva o estado atual como o perfil `name` (sobrescreve se existir)."""
    profile = snapshot_current()
    cfg = settings.get()
    cfg.profiles[name] = profile
    cfg.active_profile = name
    settings.save(cfg)
    return profile


def apply_profile(name: str) -> bool:
    """
    Ativa o perfil `name`: grava role, favoritos, preset e tier pelos
    mecanismos existentes. False se o perfil não existir.
    """
    cfg = settings.get()
    profile = cfg.profiles.get(name)
    if profile is None:
        return False
    if profile.role is not None:
        storage.write_role(profile.role)
    storage.save_heroes_to_files(list(profile.favorites), get_hero_role)
    cfg.weights_preset = profile.weights_preset
    cfg.scraper_tier = profile.scraper_tier
    cfg.active_profile = name
    settings.save(cfg)
    log.info(
        "perfil '%s' aplicado (role=%s, preset=%s)", name, profile.role, profile.weights_preset
    )
    return True


def delete_profile(name: str) -> bool:
    """Remove o perfil `name`. False se não existir."""
    cfg = settings.get()
    if name not in cfg.profiles:
        return False
    del cfg.profiles[name]
    if cfg.active_profile == name:
        cfg.active_profile = None
    settings.save(cfg)
    return True


def _list_profiles() -> None:
    cfg = settings.get()
    if not cfg.profiles:
        print("  (nenhum perfil salvo)")
        return
    for name, p in cfg.profiles.items():
        active = " (ativo)" if name == cfg.active_profile else ""
        print(
            f"  {name}{active}: role={p.role or '-'}, {len(p.favorites)} favorito(s), "
            f"preset={p.weights_preset}, tier={p.scraper_tier}"
        )


def executar(ask: Callable[[str], str] = input) -> None:
    """Menu de perfis: listar, salvar o estado atual, trocar e remover."""
    while True:
        print("\nPerfis salvos:")
        _list_profiles()
        print("\n1. Salvar o estado atual como perfil")
        print("2. Trocar para um perfil")
        print("3. Remover um perfil")
        print("4. Sair")

        choice = ask("\nOpção: ").strip()

        if choice == "1":
            name = ask("Nome do perfil: ").strip()
            if not name:
                print("✗ Nome vazio — perfil não salvo.")
                continue
            profile = save_profile(name)
            print(
                f"✓ Perfil '{name}' salvo (role={profile.role or '-'}, "
                f"{len(profile.favorites)} favorito(s), preset={profile.weights_preset})"
            )
        elif choice == "2":
            name = ask("Nome do perfil: ").strip()
            if apply_profile(name):
                print(f"✓ Perfil '{name}' ativado.")
            else:
                print(f"✗ Perfil '{name}' não existe. Use a opção 1 para criá-lo.")
        elif choice == "3":
            name = ask("Nome do perfil: ").strip()
            if delete_profile(name):
                print(f"✓ Perfil '{name}' removido.")
            else:
                print(f"✗ Perfil '{name}' não existe.")
        elif choice == "4":
            break
        else:
            print("✗ Opção inválida")
