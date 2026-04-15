import os
import sys
from typing import List, Dict, Tuple, Optional
import pandas as pd

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


def print_map() -> str:
    map_path = "map.txt"
    if not os.path.exists(map_path):
        return ""

    with open(map_path, "r", encoding="utf-8") as f:
        texto = f.read().strip()

    texto = texto.replace("-", " ").title()
    print(f"Mapa selecionado: {texto}")
    return texto

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
# Leitura de winrate + pickrate
# --------------------------
def _convert_to_float_safe(val) -> Optional[float]:
    if pd.isna(val):
        return None
    try:
        s = str(val).strip().replace(",", ".").replace("%", "")
        return float(s)
    except Exception:
        return None


def read_winrate_data(filepath: str = "winrate.xlsx") -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Lê winrate.xlsx e retorna:
      - winrate_dict: {hero: winrate_value (float)}
      - pickrate_dict: {hero: pick_score (float, já convertido para -2..2)}
    Observações:
      - Coluna A (índice 0) = nome do herói
      - Coluna E (índice 4) = winrate (numérico ou string com vírgula)
      - Coluna F (índice 5) = pickrate (pode ser percentual como 17.1 ou já score)
    """
    if not os.path.exists(filepath):
        print("Nenhum mapa será somado a pontuação final")
        print("Selecione um mapa ou atualize as winrates")
        return {}, {}

    df = pd.read_excel(filepath, sheet_name=0)

    winrate_dict: Dict[str, float] = {}
    pickrate_dict: Dict[str, float] = {}

    for _, row in df.iterrows():
        hero_name_raw = row.iloc[0] if len(row) > 0 else None
        if pd.isna(hero_name_raw):
            continue
        key = str(hero_name_raw).strip()

        # WINRATE (coluna E / índice 4)
        win_raw = row.iloc[4] if len(row) > 4 else None
        win_f = _convert_to_float_safe(win_raw)
        winrate_dict[key] = float(win_f) if win_f is not None else 0.0

        # PICKRATE (coluna F / índice 5)
        pick_raw = row.iloc[5] if len(row) > 5 else None
        pick_f = _convert_to_float_safe(pick_raw)

        # Se valor ausente, assume 0
        if pick_f is None:
            pickrate_dict[key] = 0.0
        else:
            pickrate_dict[key] = pick_f

    return winrate_dict, pickrate_dict

# --------------------------
# Cálculo de pontuação por herói (compatível)
# --------------------------
def calculate_hero_score(
    hero_name: str,
    ally_df: pd.DataFrame,
    enemy_df: pd.DataFrame,
    allies: List[str],
    enemies: List[str],
    winrate_dict: Dict[str, float],
    pickrate_dict: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    Calcula a pontuação de um herói jogável incluindo:
      - enemy_score (matchups contra inimigos)
      - ally_score  (matchups com aliados * 0.65)
      - map_winrate (valor vindo do winrate.xlsx coluna E)
      - map_pickrate (valor vindo do winrate.xlsx coluna F convertida p/ -2..2)
    pickrate_dict é opcional para compatibilidade com versões antigas.
    """
    if pickrate_dict is None:
        pickrate_dict = {}

    enemy_score = 0.0
    hero_row_enemy = enemy_df[enemy_df.iloc[:, 0] == hero_name]
    if not hero_row_enemy.empty:
        for enemy in enemies:
            if enemy in enemy_df.columns:
                value = hero_row_enemy[enemy].values[0]
                if pd.notna(value):
                    try:
                        enemy_score += float(value)
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

    map_winrate = float(winrate_dict.get(hero_name, 0.0))
    map_pickrate = float(pickrate_dict.get(hero_name, 0.0))

    total_score = enemy_score + ally_score + map_winrate + map_pickrate

    return {
        "hero": hero_name,
        "enemy_score": enemy_score,
        "ally_score": ally_score,
        "map_winrate": map_winrate,
        "map_pickrate": map_pickrate,
        "total": total_score
    }

# --------------------------
# Impressão do ranking
# --------------------------
def print_ranking(rankings: List[Dict[str, float]]) -> None:
    sorted_rankings = sorted(rankings, key=lambda x: x["total"], reverse=True)

    print("=" * 95)
    print(f"{'RANK':<6} | {'HERO':<18} | {'ENEMY':>8} | {'ALLY':>8} | {'MAP':>8} | {'PICK':>8} | {'TOTAL':>8}")
    print("=" * 95)
    for rank, hero_data in enumerate(sorted_rankings, start=1):
        print(
            f"{rank:<6} | "
            f"{hero_data['hero']:<18} | "
            f"{hero_data['enemy_score']:>8.2f} | "
            f"{hero_data['ally_score']:>8.2f} | "
            f"{hero_data['map_winrate']:>8.2f} | "
            f"{hero_data['map_pickrate']:>8.2f} | "
            f"{hero_data['total']:>8.2f}"
        )
    print("-" * 95)

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

    mapa_formatado = print_map()

    # Leitura de winrate + pickrate (compatível)
    res = read_winrate_data()
    if isinstance(res, tuple) and len(res) == 2:
        winrate_dict, pickrate_dict = res
    else:
        # Compatibilidade (caso read_winrate_data retorne apenas um dict)
        winrate_dict = res if isinstance(res, dict) else {}
        pickrate_dict = {}

    rankings: List[Dict[str, float]] = []
    for hero in playable_heroes:
        score_data = calculate_hero_score(
            hero,
            ally_df,
            enemy_df,
            allies,
            enemies,
            winrate_dict,
            pickrate_dict
        )
        rankings.append(score_data)

    print_ranking(rankings)


if __name__ == "__main__":
    run_hero_ranking()
