import os
import sys
from typing import List, Dict, Optional
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


# --------------------------
# Leitura de arquivos de entrada
# --------------------------
def read_lineup(filepath: str = "lineup.txt"):
    """
    Lê o lineup.txt.
    - Linhas [:4]  → enemies (time adversário que enfrentará o hero)
    - Linhas [4:9] → allies  (time aliado do hero, incluindo ele mesmo)
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    enemies = lines[:4]
    allies  = lines[4:9]
    return allies, enemies


def read_heroes_ally_data(filepath: str = "heroes ally.xlsx") -> pd.DataFrame:
    final_path = resource_path(filepath)
    return pd.read_excel(final_path, sheet_name=0, header=0)


def read_heroes_enemy_data(filepath: str = "heroes enemy.xlsx") -> pd.DataFrame:
    final_path = resource_path(filepath)
    return pd.read_excel(final_path, sheet_name=0, header=0)


# --------------------------
# Cálculo de pontuação do herói
# --------------------------
def calculate_hero_score(
    hero_name: str,
    ally_df: pd.DataFrame,
    enemy_df: pd.DataFrame,
    allies: List[str],
    enemies: List[str]
) -> Dict[str, float]:
    """
    Calcula a pontuação do hero passado como argumento:
      - enemy_score: matchups do hero contra os enemies (linhas [:4])
      - ally_score:  sinergia do hero com os allies (linhas [4:9] sem o próprio hero) * 0.65
    """
    # --- enemy_score ---
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

    # --- ally_score ---
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
# Função principal exportada
# --------------------------
def executar(hero: str) -> float:
    """
    Avalia o hero informado contra o lineup atual.

    Parâmetros
    ----------
    hero : str
        Nome do herói a ser avaliado (buscado na primeira coluna das planilhas).

    Retorna
    -------
    float
        O enemy_score calculado para o hero.
    """
    # Lê o lineup
    try:
        allies_raw, enemies = read_lineup()
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem primeiro.")
        return 0.0

    # Remove o próprio hero da lista de aliados (caso apareça)
    allies = [a for a in allies_raw if a != hero]
    #print(f"Enemies ([:4]): {', '.join(enemies)}")
    #print(f"Allies  ([4:9] sem o hero): {', '.join(allies)}\n")

    # Lê as planilhas
    try:
        ally_df  = read_heroes_ally_data()
        enemy_df = read_heroes_enemy_data()
    except FileNotFoundError as e:
        print(f"ERRO CRÍTICO: Não foi possível ler as planilhas de dados: {e}")
        return 0.0

    # Calcula o score
    score_data = calculate_hero_score(
        hero_name=hero,
        ally_df=ally_df,
        enemy_df=enemy_df,
        allies=allies,
        enemies=enemies
    )

    #print(f"enemy_score : {score_data['enemy_score']:.2f}")
    #print(f"ally_score  : {score_data['ally_score']:.2f}")
    #print(f"total       : {score_data['total']:.2f}")

    if score_data["total"] >= 0.0:
        mult = (score_data["total"] / 4) + 1
    else:
        mult = 1 - 0.125 * abs(score_data["total"])

    print(f"Heroi inimigo avaliado : {hero} -> Mult: {mult:.2f}")

    return mult