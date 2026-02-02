import pandas as pd
from typing import List, Dict, Tuple
import os
import sys

def print_map():
    # Caminho do arquivo map.txt
    map_path = "map.txt"
    if not os.path.exists(map_path):
        # Se não existir, retorna dict vazio
        return {}

    # Abre e lê o arquivo
    with open(map_path, "r", encoding="utf-8") as arquivo:
        texto = arquivo.read().strip()

    # Substitui "-" por espaço
    texto = texto.replace("-", " ")

    # Coloca a primeira letra de cada palavra em maiúscula
    texto = texto.title()
    print(f"Mapa selecionado: {texto}")

    return

# Função "para executavel", mas tambem funciona no python normal
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS # Só existe quando vira .exe e extrai os arquivos para um pasta temporaria e esta variavel anota o caminho
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path) # Mostra o caminho final

def read_role() -> str: #Função que descobre qual role o usuario escolheu
    role_file = "Roles.txt"
    
    if not os.path.exists(role_file): # Não achou o Roles.txt
        print("Arquivo 'Roles.txt' não encontrado!")
        print("Por favor, defina sua Role (DPS, Support, Tank ou AllRoles)")
        return None
    
    with open(role_file, 'r', encoding='utf-8') as f:
        role = f.read().strip()
    
    if not role: # Roles.txt vazio
        print("Arquivo 'Roles.txt' está vazio!")
        print("Por favor, defina sua Role (DPS, Support, Tank ou AllRoles)")
        return None
    
    role_heroes_file = f"{role}.txt" # Pega o que tem dentro do Role.txt e encontra um arquivo com esse nome
    if not os.path.exists(role_heroes_file): # Se não existir = erro
        print(f"Arquivo '{role_heroes_file}' não encontrado!")
        print("Por favor, defina seus Personagens Favoritos.")
        return None
    
    return role


def read_playable_heroes(role: str) -> List[str]:

    role_file = f"{role}.txt" # Lê os personagens favoritos da Role escolhida
    
    with open(role_file, 'r', encoding='utf-8') as f:
        heroes = [line.strip() for line in f.readlines() if line.strip()]
    
    return heroes # Retorna os personagens


def read_lineup(filepath: str = "lineup.txt") -> Tuple[List[str], List[str]]: # Lê o time inimigo e aliado
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines()]
    
    allies = lines[:4] # 4 primeiros são aliados
    enemies = lines[4:9] # 5 ultimos sao inimigos
    
    return allies, enemies # Retorna os aliados e inimigos

# Lê o arquivo heroes ally.xlsx com os matchups de aliados
def read_heroes_ally_data(filepath: str = "heroes ally.xlsx") -> pd.DataFrame:
    final_path = resource_path(filepath) # resource_path acha o heroes ally.xlsx que é pré-definido
    df = pd.read_excel(final_path, sheet_name=0, header=0) # primeira coluna = nome dos herois, outras colunas = matchups
    return df

# Lê o arquivo heroes enemy.xlsx com os matchups de aliados
def read_heroes_enemy_data(filepath: str = "heroes enemy.xlsx") -> pd.DataFrame:
    final_path = resource_path(filepath) # resource_path acha o heroes enemy.xlsx que é pré-definido
    df = pd.read_excel(final_path, sheet_name=0, header=0) # primeira coluna = nome dos herois, outras colunas = matchups
    return df

# Lê o arquivo winrate.xlsx e retorna dicionário {herói: winrate} e {herói: pickrate_numérica}
def read_winrate_data(filepath: str = "winrate.xlsx") -> Tuple[Dict[str, float], Dict[str, float]]:
    if not os.path.exists(filepath):
        print('Nenhum mapa será somado a pontuação final')
        print('Selecione um mapa ou atualize as winrates')
        return {}, {}

    df = pd.read_excel(filepath, sheet_name=0)
    winrate_dict = {}
    pickrate_dict = {}

    for _, row in df.iterrows():
        hero_name = row.iloc[0]  # Coluna A (nome)
        winrate_value = row.iloc[4] if len(row) > 4 else None # Coluna E (winrate)
        pickrate_value = row.iloc[5] if len(row) > 5 else None # Coluna F (pickrate)

        if pd.notna(hero_name):
            key = str(hero_name).strip()
            # Processa winrate
            if pd.notna(winrate_value):
                # Converter valor para string e trocar vírgula por ponto
                win_str = str(winrate_value).replace(',', '.')
                try:
                    winrate_dict[key] = float(win_str)
                except (ValueError, TypeError):
                    winrate_dict[key] = 0.0
            else:
                winrate_dict[key] = 0.0

            # Processa pickrate (pode ser score já convertido ou %; tratamos ambos)
            if pd.notna(pickrate_value):
                pick_str = str(pickrate_value).strip().replace(',', '.')
                # Se tiver um símbolo de porcentagem, removemos
                pick_str = pick_str.replace('%', '')
                try:
                    pick_val = float(pick_str)
                except (ValueError, TypeError):
                    pick_val = 0.0
                pickrate_dict[key] = pick_val
            else:
                pickrate_dict[key] = 0.0

    return winrate_dict, pickrate_dict


def calculate_hero_score(
    hero_name: str,
    ally_df: pd.DataFrame,
    enemy_df: pd.DataFrame,
    allies: List[str],
    enemies: List[str],
    winrate_dict: Dict[str, float],
    pickrate_dict: Dict[str, float]
) -> Dict[str, float]:
    """
    Calcula a pontuação de um herói jogável incluindo:
      - enemy_score (matchups contra inimigos)
      - ally_score  (matchups com aliados * 0.65)
      - map_winrate (valor vindo do winrate.xlsx coluna E)
      - map_pickrate (valor vindo do winrate.xlsx coluna F)
    """
    enemy_score = 0.0
    hero_row_enemy = enemy_df[enemy_df.iloc[:, 0] == hero_name]
    if not hero_row_enemy.empty:
        for enemy in enemies:
            if enemy in enemy_df.columns:
                value = hero_row_enemy[enemy].values[0]
                if pd.notna(value):
                    enemy_score += float(value)

    ally_score = 0.0
    hero_row_ally = ally_df[ally_df.iloc[:, 0] == hero_name]
    if not hero_row_ally.empty:
        for ally in allies:
            if ally in ally_df.columns:
                value = hero_row_ally[ally].values[0] * 0.65
                if pd.notna(value):
                    ally_score += float(value)

    map_winrate = winrate_dict.get(hero_name, 0.0)
    map_pickrate = pickrate_dict.get(hero_name, 0.0)

    total_score = enemy_score + ally_score + map_winrate + map_pickrate

    return {
        'hero': hero_name,
        'enemy_score': enemy_score,
        'ally_score': ally_score,
        'map_winrate': map_winrate,
        'map_pickrate': map_pickrate,
        'total': total_score
    }


def print_ranking(rankings: List[Dict[str, float]]) -> None:
    """
    Imprime o ranking mostrando agora também a coluna PICK (map_pickrate).
    """
    sorted_rankings = sorted(rankings, key=lambda x: x['total'], reverse=True)

    print("=" * 85)
    print(f"{'RANK':<6} | {'HERO':<15} | {'ENEMY':>8} | {'ALLY':>8} | {'MAP':>8} | {'PICK':>8} | {'TOTAL':>8}")
    print("=" * 85)

    for rank, hero_data in enumerate(sorted_rankings, start=1):
        print(
            f"{rank:<6} | "
            f"{hero_data['hero']:<15} | "
            f"{hero_data['enemy_score']:>8.2f} | "
            f"{hero_data['ally_score']:>8.2f} | "
            f"{hero_data['map_winrate']:>8.2f} | "
            f"{hero_data['map_pickrate']:>8.2f} | "
            f"{hero_data['total']:>8.2f}"
        )

    print("-" * 85)


def run_hero_ranking():
    """
    Função principal que executa todo o processo de ranking
    """
    # Ler a role do jogador
    role = read_role()
    if role is None:
        return
    
    print(f"Role selecionada: {role}")
    print()
    
    # Ler heróis jogáveis da role
    playable_heroes = read_playable_heroes(role)
    print(f"Heróis disponíveis: {', '.join(playable_heroes)}")
    print()
    
    # Ler dados
    try:
        allies, enemies = read_lineup()
        print(f"Aliados: {', '.join(allies)}")
        print(f"Inimigos: {', '.join(enemies)}")
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem (TAB+1) primeiro.")
        return
    print()
    
    # Tratamento de erro caso os excels não existam
    try:
        ally_df = read_heroes_ally_data()
        enemy_df = read_heroes_enemy_data()
    except FileNotFoundError as e:
        print(f"ERRO CRÍTICO: Não foi possível ler as planilhas de dados: {e}")
        return
    
    print_map()

    winrate_dict = read_winrate_data()
    
    # Calcular pontuação para cada herói jogável
    rankings = []
    for hero in playable_heroes:
        score_data = calculate_hero_score(
            hero,
            ally_df,
            enemy_df,
            allies,
            enemies,
            winrate_dict
        )
        rankings.append(score_data)
    
    # Imprimir ranking
    print_ranking(rankings)

if __name__ == "__main__":
    run_hero_ranking()