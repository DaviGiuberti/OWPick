"""xlsx_to_csv.py — Converte as matrizes .xlsx (fonte de EDIÇÃO) nos .csv que o
programa LÊ em runtime (tarefa 5.1). Ferramenta OFFLINE de desenvolvimento.

Fluxo do autor:
  1. Edita as matrizes em `data/heroes ally.xlsx` / `data/heroes enemy.xlsx`.
  2. Roda este script (uma vez, manualmente) ANTES de cada atualização/build.
  3. O programa passa a ler os `.csv` gerados (`data/synergies.csv`,
     `data/counters.csv`).

IMPORTANTE (requisito do autor): nem os `.xlsx` nem este script vão para o
`.exe`/`.zip` finais — NÃO constam no overwatch.spec nem no updater.py. Apenas os
`.csv` são empacotados. Requer `openpyxl` (grupo `dev` do pyproject).

Uso:
    python tools/xlsx_to_csv.py            # converte ambas as matrizes
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Raiz do repositório (tools/ vive na raiz).
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# (xlsx de edição, csv de runtime). O índice (col 0) é o herói da LINHA; as
# colunas são os heróis; index_col=0 preserva o mesmo formato lido por
# infra.datasource + core.heroes.build_matrix_dict.
CONVERSIONS = [
    ("heroes ally.xlsx", "synergies.csv"),  # matriz de SINERGIAS (aliados)
    ("heroes enemy.xlsx", "counters.csv"),  # matriz de COUNTERS (inimigos)
]


def convert_one(xlsx_name: str, csv_name: str) -> None:
    src = DATA_DIR / xlsx_name
    dst = DATA_DIR / csv_name
    if not src.exists():
        raise FileNotFoundError(f"planilha de edição não encontrada: {src}")
    df = pd.read_excel(src, sheet_name=0, index_col=0)
    df.to_csv(dst, encoding="utf-8")
    print(f"OK: {src.name} ({df.shape[0]}x{df.shape[1]}) -> {dst.name}")


def main() -> None:
    for xlsx_name, csv_name in CONVERSIONS:
        convert_one(xlsx_name, csv_name)
    print("Conversão concluída. Os .csv são a fonte lida em runtime.")


if __name__ == "__main__":
    main()
