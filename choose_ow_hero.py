import os
import sys
from typing import List, Dict, Tuple, Optional
import pandas as pd
from enemy_mult import executar

# --------------------------
# Utilitários
# --------------------------
def resource_path(relative_path: str) -> str:
    """
    Retorna o caminho absoluto para o arquivo, tanto em execução normal quanto
    quando empacotado em .exe (PyInstaller).
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --------------------------
# Leitura de arquivos de entrada
# --------------------------
def read_role() -> Optional[str]:
    role_file = "Roles.txt"
    if not os.path.exists(role_file):
        print("Arquivo 'Roles.txt' não encontrado!")
        print("Por favor, defina sua Role (DPS, Support, Tank ou AllRoles)")
        return None

    with open(role_file, "r", encoding="utf-8") as f:
        role = f.read().strip()

    if not role:
        print("Arquivo 'Roles.txt' está vazio!")
        print("Por favor, defina sua Role (DPS, Support, Tank ou AllRoles)")
        return None

    role_heroes_file = f"{role}.txt"
    if not os.path.exists(role_heroes_file):
        print(f"Arquivo '{role_heroes_file}' não encontrado!")
        print("Por favor, defina seus Personagens Favoritos.")
        return None

    return role


def read_playable_heroes(role: str) -> List[str]:
    role_file = f"{role}.txt"
    with open(role_file, "r", encoding="utf-8") as f:
        heroes = [line.strip() for line in f.readlines() if line.strip()]
    return heroes


def read_lineup(filepath: str = "lineup.txt") -> Tuple[List[str], List[str]]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    allies = lines[:4]
    enemies = lines[4:9]
    return allies, enemies


def read_heroes_ally_data(filepath: str = "heroes ally.xlsx") -> pd.DataFrame:
    final_path = resource_path(filepath)
    return pd.read_excel(final_path, sheet_name=0, header=0)


def read_heroes_enemy_data(filepath: str = "heroes enemy.xlsx") -> pd.DataFrame:
    final_path = resource_path(filepath)
    return pd.read_excel(final_path, sheet_name=0, header=0)

# --------------------------
# Leitura do arquivo de prioridade e cálculo dos multiplicadores
# --------------------------
def read_priority_mode() -> bool:
    """
    Retorna True se 'prioritize.txt' existir e contiver exatamente '1'.
    Caso contrário, retorna False.
    """
    prioritize_file = "prioritize.txt"
    if not os.path.exists(prioritize_file):
        return False
    with open(prioritize_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    return content == "1"


def build_enemy_multipliers(enemies: List[str], priority_mode: bool) -> Dict[str, float]:
    """
    Executa executar(enemy) uma única vez por enemy se priority_mode for True,
    salvando o resultado em um dicionário. Caso contrário, todos os
    multiplicadores são 1.
    """
    multipliers: Dict[str, float] = {}
    for enemy in enemies:
        if priority_mode:
            try:
                multipliers[enemy] = float(executar(enemy))
            except Exception:
                multipliers[enemy] = 1.0
        else:
            multipliers[enemy] = 1.0
    return multipliers

# --------------------------
# Cálculo de pontuação por herói
# --------------------------
def calculate_hero_score(
    hero_name: str,
    ally_df: pd.DataFrame,
    enemy_df: pd.DataFrame,
    allies: List[str],
    enemies: List[str],
    enemy_multipliers: Dict[str, float]
) -> Dict[str, float]:
    """
    Calcula a pontuação de um herói jogável incluindo apenas:
      - enemy_score (matchups contra inimigos * multiplicador do enemy)
      - ally_score  (matchups com aliados * 0.65)

    O multiplicador de cada enemy é 1 por padrão, ou o valor retornado por
    executar(enemy) quando o modo de prioridade está ativo.
    """
    enemy_score = 0.0
    hero_row_enemy = enemy_df[enemy_df.iloc[:, 0] == hero_name]
    if not hero_row_enemy.empty:
        for enemy in enemies:
            if enemy in enemy_df.columns:
                value = hero_row_enemy[enemy].values[0]
                if pd.notna(value):
                    try:
                        multiplier = enemy_multipliers.get(enemy, 1.0)
                        enemy_score += float(value) * multiplier
                    except Exception:
                        pass

    ally_score = 0.0
    hero_row_ally = ally_df[ally_df.iloc[:, 0] == hero_name]
    if not hero_row_ally.empty:
        for ally in allies:
            if ally in ally_df.columns:
                value = hero_row_ally[ally].values[0]
                if pd.notna(value):
                    try:
                        ally_score += float(value) * 0.65
                    except Exception:
                        pass

    total_score = enemy_score + ally_score

    return {
        "hero": hero_name,
        "enemy_score": enemy_score,
        "ally_score": ally_score,
        "total": total_score
    }

# --------------------------
# Impressão do ranking
# --------------------------
def print_ranking(rankings: List[Dict[str, float]]) -> None:
    sorted_rankings = sorted(rankings, key=lambda x: x["total"], reverse=True)

    print("=" * 65)
    print(f"{'RANK':<6} | {'HERO':<18} | {'ENEMY':>8} | {'ALLY':>8} | {'TOTAL':>8}")
    print("=" * 65)
    for rank, hero_data in enumerate(sorted_rankings, start=1):
        print(
            f"{rank:<6} | "
            f"{hero_data['hero']:<18} | "
            f"{hero_data['enemy_score']:>8.2f} | "
            f"{hero_data['ally_score']:>8.2f} | "
            f"{hero_data['total']:>8.2f}"
        )
    print("-" * 65)

# --------------------------
# Fluxo principal
# --------------------------
def run_hero_ranking():
    role = read_role()
    if role is None:
        return
    print(f"Role selecionada: {role}\n")

    playable_heroes = read_playable_heroes(role)
    print(f"Heróis disponíveis: {', '.join(playable_heroes)}\n")

    try:
        allies, enemies = read_lineup()
        print(f"Aliados: {', '.join(allies)}")
        print(f"Inimigos: {', '.join(enemies)}\n")
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem (TAB+1) primeiro.")
        return

    try:
        ally_df = read_heroes_ally_data()
        enemy_df = read_heroes_enemy_data()
    except FileNotFoundError as e:
        print(f"ERRO CRÍTICO: Não foi possível ler as planilhas de dados: {e}")
        return

    # Verifica o modo de prioridade e calcula os multiplicadores uma única vez
    priority_mode = read_priority_mode()
    if priority_mode:
        print("Modo de prioridade ATIVO: multiplicadores de enemy calculados via executar().\n")
    enemy_multipliers = build_enemy_multipliers(enemies, priority_mode)

    rankings: List[Dict[str, float]] = []
    for hero in playable_heroes:
        score_data = calculate_hero_score(
            hero,
            ally_df,
            enemy_df,
            allies,
            enemies,
            enemy_multipliers
        )
        rankings.append(score_data)

    print_ranking(rankings)


if __name__ == "__main__":
    run_hero_ranking()