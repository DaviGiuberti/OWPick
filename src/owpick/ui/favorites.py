"""favorites.py — Menu de heróis favoritos (camada ui).

A entrada do usuário é INJETÁVEL (`ask`) para permitir testes automatizados;
o default real é input(), então em produção o comportamento não muda em nada.
A persistência (ALL/DPS/SUP/TANK.txt) vive em infra.storage.
"""

from __future__ import annotations

from collections.abc import Callable

from rapidfuzz import fuzz, process

from owpick.core.heroes import get_all_heroes, get_hero_role, load_heroes_roles, normalize_hero_name
from owpick.infra import storage
from owpick.log import get_logger

log = get_logger("favorites")

# Fonte única de heróis: core.heroes (constante embutida HEROES_ROLES).
HEROES = load_heroes_roles()

# Limiar do fuzzy match da entrada do usuário (escala 0-100 do rapidfuzz;
# equivale ao antigo cutoff 0.4 do difflib.get_close_matches).
FUZZY_MIN_SCORE = 40.0


# Encontra o herói que mais se parece com a entrada do usuário
def find_best_match(user_input: str, normalized_heroes: dict[str, str]) -> str | None:
    if not user_input.strip():  # entrada vazia sai
        return None

    normalized_input = normalize_hero_name(user_input)  # normalização canônica

    # Tenta encontrar correspondências exatas primeiro
    if normalized_input in normalized_heroes:
        return normalized_heroes[normalized_input]

    # Melhor correspondência fuzzy (rapidfuzz — mesma lib do matching de mapa)
    match = process.extractOne(
        normalized_input,
        normalized_heroes.keys(),
        scorer=fuzz.ratio,
        score_cutoff=FUZZY_MIN_SCORE,
    )
    if match:
        return normalized_heroes[match[0]]

    return None


def _save(favorites: list[str]) -> None:
    storage.save_heroes_to_files(favorites, get_hero_role)


# Adiciona um herói aos favoritos e salva direto nos arquivos
def add_favorite(hero_name: str) -> bool:
    favorites = storage.load_favorites()
    if hero_name not in favorites:
        favorites.append(hero_name)
        _save(favorites)
        print(f"✓ {hero_name} adicionado")
        return True
    print(f"✗ {hero_name} já existe")
    return False


# Remove um herói dos favoritos e atualiza os arquivos
def remove_favorite(hero_name: str) -> bool:
    favorites = storage.load_favorites()
    if hero_name in favorites:
        favorites.remove(hero_name)
        _save(favorites)
        print(f"✓ {hero_name} removido")
        return True
    print(f"✗ {hero_name} não está nos favoritos")
    return False


# Lista todos os heróis favoritos
def list_favorites() -> None:
    favorites = storage.load_favorites()
    if favorites:
        for hero in favorites:
            print(f"  {hero} ({get_hero_role(hero)})")
    else:
        print("  Nenhum favorito")


# Menu para adicionar em lote uma função inteira ou todos os heróis
def add_role_or_all_menu(ask: Callable[[str], str]) -> str | None:
    print("\nEscolha a função para adicionar:")
    print("  1 - DPS")
    print("  2 - Suporte")
    print("  3 - Tanque")
    print("  4 - Todos os personagens")
    sub = ask("\n> ").strip()
    return {"1": "DPS", "2": "SUP", "3": "TANK", "4": "ALL"}.get(sub)


# Adiciona em lote uma função inteira ou todos os heróis
def add_role_or_all(ask: Callable[[str], str] = input) -> bool:
    role_key = add_role_or_all_menu(ask)
    if not role_key:
        print("✗ Função não reconhecida")
        return False
    to_add = get_all_heroes() if role_key == "ALL" else HEROES.get(role_key, [])
    if not to_add:
        print("✗ Nenhum herói para adicionar nessa função")
        return False
    favorites = storage.load_favorites()
    added = [h for h in to_add if h not in favorites]
    if added:
        favorites.extend(added)
        _save(favorites)
        print(f"✓ {len(added)} herói(s) adicionados: {', '.join(added)}")
    else:
        print("✗ Todos já estavam nos favoritos")
    return True


# Menu principal de favoritos
def executar(ask: Callable[[str], str] = input) -> None:
    all_heroes = get_all_heroes()
    # Normaliza todos os personagens, para o find_best_match
    normalized_heroes = {normalize_hero_name(hero): hero for hero in all_heroes}

    while True:
        print("\n1. Adicionar herói")
        print("2. Remover herói")
        print("3. Ver favoritos")
        print("4. Adicionar função inteira")
        print("5. Sair")

        choice = ask("\nOpção: ").strip()

        if choice == "1":
            user_input = ask("Herói: ").strip()
            match = find_best_match(user_input, normalized_heroes)
            if match:
                add_favorite(match)
            else:
                print("✗ Herói não encontrado")

        elif choice == "2":
            user_input = ask("Herói: ").strip()
            match = find_best_match(user_input, normalized_heroes)
            if match:
                remove_favorite(match)
            else:
                print("✗ Herói não encontrado")

        elif choice == "3":
            print("\nFavoritos:")
            list_favorites()
        elif choice == "4":
            add_role_or_all(ask)
        elif choice == "5":
            break

        else:
            print("✗ Opção inválida")


if __name__ == "__main__":
    executar()
