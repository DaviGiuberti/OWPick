from difflib import get_close_matches
import unicodedata
import os

# Lista completa de heróis do Overwatch organizados por função
HEROES = {
    "DPS": [
        "Anran", "Ashe", "Bastion", "Cassidy", "Echo", "Emre", "Freja", "Genji", "Hanzo",
        "Junkrat", "Mei", "Pharah", "Reaper", "Sierra", "Sojourn", "Soldier 76",
        "Sombra", "Symmetra", "Torbjörn", "Tracer", "Vendetta", "Venture",
        "Widowmaker"
    ],
    "SUP": [
        "Ana", "Baptiste", "Brigitte", "Illari", "Jetpack Cat", "Juno", "Kiriko",
        "Lifeweaver", "Lúcio", "Mercy", "Mizuki", "Moira", "Wuyang", "Zenyatta"
    ],
    "TANK": [
        "DVa", "Domina", "Doomfist", "Hazard", "Junker Queen", "Mauga", "Orisa",
        "Ramattra", "Reinhardt", "Roadhog", "Sigma", "Winston",
        "Wrecking Ball", "Zarya"
    ]
}

FAVORITES_FILE = "ALL.txt"  # Agora ALL.txt é o arquivo de favoritos

# Remove acentos, converte para minusculo e remove espaços extras. Ajuda no find_best_match
def normalize_text(text):
    nfkd = unicodedata.normalize('NFKD', text)
    text_no_accents = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    return text_no_accents.lower().strip()

# Cria uma lista com todos os heróis, independente da função.
def get_all_heroes():
    all_heroes = []
    for role_heroes in HEROES.values():
        all_heroes.extend(role_heroes)
    return all_heroes

# Descobre se o herói digitado é DPS, SUP ou TANK.
def get_hero_role(hero_name):
    for role, heroes in HEROES.items():
        if hero_name in heroes:
            return role
    return None

# Encontra o herói que mais se parece com a entrada do usuário
def find_best_match(user_input, normalized_heroes):
    if not user_input.strip(): #entrada vazia sai
        return None
    
    normalized_input = normalize_text(user_input) # Normalização
    
    # Tenta encontrar correspondências exatas primeiro
    if normalized_input in normalized_heroes:
        return normalized_heroes[normalized_input]
    
    # Encontra a melhor correspondencia com um cutoff de 0.4
    matches = get_close_matches(normalized_input, normalized_heroes.keys(), n=1, cutoff=0.4)
    
    if matches:
        return normalized_heroes[matches[0]]
    
    return None

#Salva os heróis nos arquivos apropriados baseado em suas funções
def save_heroes_to_files(heroes_list):
    # Remove duplicatas mantendo a ordem
    heroes_list = list(dict.fromkeys(heroes_list))
    
    # Organiza os heróis por função
    heroes_by_role = {"DPS": [], "SUP": [], "TANK": []}
    
    for hero in heroes_list:
        role = get_hero_role(hero)
        if role:
            heroes_by_role[role].append(hero)
    
    # Salva cada função em seu arquivo correspondente
    for role, filename in [("DPS", "DPS.txt"), ("SUP", "SUP.txt"), ("TANK", "TANK.txt")]:
        # abre em 'w' para sobrescrever; se não houver heróis para a role, cria arquivo vazio
        with open(filename, 'w', encoding='utf-8') as f:
            if heroes_by_role[role]:
                f.write('\n'.join(heroes_by_role[role]))
    
    # Salva todos os heróis em ALL.txt (arquivo de favoritos)
    with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
        if heroes_list:
            f.write('\n'.join(heroes_list))

# Carrega a lista de heróis favoritos a partir do ALL.txt
def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        try:
            with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except:
            return []
    return []


# Adiciona um herói aos favoritos e salva direto nos arquivos
def add_favorite(hero_name):
    favorites = load_favorites()
    if hero_name not in favorites: # Se o heroi não estiver em favoritos, ele é adicionado
        favorites.append(hero_name)
        save_heroes_to_files(favorites)
        print(f"✓ {hero_name} adicionado")
        return True
    else:
        print(f"✗ {hero_name} já existe")
        return False

# Remove um herói dos favoritos e atualiza os arquivos
def remove_favorite(hero_name):
    favorites = load_favorites()
    if hero_name in favorites:
        favorites.remove(hero_name)
        save_heroes_to_files(favorites)
        print(f"✓ {hero_name} removido")
        return True
    else:
        print(f"✗ {hero_name} não está nos favoritos")
        return False

# Lista todos os heróis favoritos
def list_favorites():
    favorites = load_favorites()
    if favorites:
        for hero in favorites:
            role = get_hero_role(hero)
            print(f"  {hero} ({role})")
    else:
        print("  Nenhum favorito")

# Adiciona em lote uma função inteira ou todos os heróis
def add_role_or_all():
    role_key = add_role_or_all_menu()
    if not role_key:
        print("✗ Função não reconhecida")
        return False
    if role_key == "ALL":
        to_add = get_all_heroes()
    else:
        to_add = HEROES.get(role_key, [])
    if not to_add:
        print("✗ Nenhum herói para adicionar nessa função")
        return False
    favorites = load_favorites()
    added = []
    for h in to_add:
        if h not in favorites:
            favorites.append(h)
            added.append(h)
    if added:
        save_heroes_to_files(favorites)
        print(f"✓ {len(added)} herói(s) adicionados: {', '.join(added)}")
    else:
        print("✗ Todos já estavam nos favoritos")
    return True

# Menu para adicionar em lote uma função inteira ou todos os heróis
def add_role_or_all_menu():
    print("\nEscolha a função para adicionar:")
    print("  1 - DPS")
    print("  2 - Suporte")
    print("  3 - Tanque")
    print("  4 - Todos os personagens")
    sub = input("\n> ").strip()
    if sub == '1':
        return 'DPS'
    elif sub == '2':
        return 'SUP'
    elif sub == '3':
        return 'TANK'
    elif sub == '4':
        return 'ALL'
    return None

# Main
def executar():
    all_heroes = get_all_heroes()
    # Normaliza todos os personagens, para o find_best_match
    normalized_heroes = {normalize_text(hero): hero for hero in all_heroes}

    while True:
        print("\n1. Adicionar herói")
        print("2. Remover herói")
        print("3. Ver favoritos")
        print("4. Adicionar função inteira inteira")
        print("5. Sair")
        
        choice = input("\nOpção: ").strip()
        
        if choice == "1":
            user_input = input("Herói: ").strip()
            match = find_best_match(user_input, normalized_heroes)
            if match:
                add_favorite(match)
            else:
                print("✗ Herói não encontrado")
        
        elif choice == "2":
            user_input = input("Herói: ").strip()
            match = find_best_match(user_input, normalized_heroes)
            if match:
                remove_favorite(match)
            else:
                print("✗ Herói não encontrado")
        
        elif choice == "3":
            print("\nFavoritos:")
            list_favorites()
        elif choice == '4':
            add_role_or_all()
        elif choice == "5":
            break
        
        else:
            print("✗ Opção inválida")

if __name__ == "__main__":
    executar()
