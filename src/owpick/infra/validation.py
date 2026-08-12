"""validation.py — Validação das matrizes e dados na carga (tarefa 5.2).

Verifica, com AVISOS CLAROS do que está faltando/errado:

  - matrizes (synergies/counters): heróis das linhas E colunas == HEROES_ROLES
    (⊆ e ⊇, após normalização) — pega typos históricos (Illarri/Rroadhog) como
    linhas/colunas órfãs e heróis ausentes. As colunas são conferidas contra o
    CABEÇALHO do CSV, não contra os valores presentes: um herói ainda SEM dados
    (linha/coluna vazias) continua sendo uma coluna válida;
  - stats_inputs.csv: cobre os 29 mapas e as roles esperadas (DPS/TANK/SUP);
  - templates: todo herói tem retrato no lineup (720p E 2k, na role certa) e um
    ícone de ban em assets/heroes/bans/.

Cada função devolve uma lista de PROBLEMAS (strings legíveis). Lista vazia = ok.
Usado nos testes (rede da 1.3) e, opcionalmente, no boot em modo --debug.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from owpick.core.heroes import (
    HEROES_ROLES,
    get_all_heroes,
    get_map_names,
    normalize_hero_name,
)
from owpick.infra import datasource
from owpick.infra.resources import resource_path

# Role (HEROES_ROLES) -> subpasta de templates do lineup.
_ROLE_TO_FOLDER = {"DPS": "dps", "TANK": "tank", "SUP": "sup"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def _expected_hero_keys() -> set[str]:
    return {normalize_hero_name(h) for h in get_all_heroes()}


def validate_matrix(
    matrix: dict[str, dict[str, float]], name: str, columns: Iterable[str] | None = None
) -> list[str]:
    """Valida uma matriz normalizada (linhas E colunas) contra HEROES_ROLES.

    `columns` é o CABEÇALHO real da planilha/CSV. Passe-o sempre que ele estiver
    disponível: `build_matrix_dict` descarta as células vazias, então uma coluna
    que existe mas ainda não tem NENHUM dado (herói recém-adicionado) sumiria da
    matriz normalizada e seria reportada como "ausente" — um falso positivo. Sem
    o parâmetro, as colunas são inferidas dos valores presentes (comportamento
    histórico, mantido para matrizes sintéticas dos testes).
    """
    problems: list[str] = []
    expected = _expected_hero_keys()

    row_keys = set(matrix)
    col_keys: set[str] = set()
    if columns is not None:
        col_keys = {normalize_hero_name(str(c)) for c in columns}
    else:
        for row in matrix.values():
            col_keys |= set(row)

    for label, keys in (("linha", row_keys), ("coluna", col_keys)):
        missing = expected - keys
        orphan = keys - expected
        if missing:
            problems.append(f"[{name}] heróis AUSENTES nas {label}s: {', '.join(sorted(missing))}")
        if orphan:
            problems.append(
                f"[{name}] {label}s ÓRFÃS (herói inexistente/typo): {', '.join(sorted(orphan))}"
            )
    return problems


def validate_stats(map_names: list[str] | None = None) -> list[str]:
    """Valida que stats_inputs.csv cobre os 29 mapas e as roles esperadas."""
    problems: list[str] = []
    try:
        df = datasource.read_stats_inputs()
    except Exception as e:  # noqa: BLE001
        return [f"[stats] não foi possível ler stats_inputs.csv: {e}"]

    expected_maps = {normalize_hero_name(m) for m in (map_names or get_map_names())}
    present_maps = {normalize_hero_name(str(m)) for m in df["map"].dropna().unique()}
    missing_maps = expected_maps - present_maps
    if missing_maps:
        problems.append(
            f"[stats] mapas SEM dados em stats_inputs.csv: {len(missing_maps)} "
            f"({', '.join(sorted(missing_maps))})"
        )

    expected_roles = set(HEROES_ROLES)  # DPS/TANK/SUP
    present_roles = {str(r).upper() for r in df["role"].dropna().unique()}
    missing_roles = expected_roles - present_roles
    if missing_roles:
        problems.append(
            f"[stats] roles AUSENTES em stats_inputs.csv: {', '.join(sorted(missing_roles))}"
        )
    return problems


def _has_template(directory: Path, hero_key: str) -> bool:
    if not directory.is_dir():
        return False
    for p in directory.iterdir():
        if p.suffix.lower() in _IMAGE_SUFFIXES and normalize_hero_name(p.stem) == hero_key:
            return True
    return False


def validate_templates(base_dir: Path | None = None) -> list[str]:
    """Valida que todo herói tem retrato de lineup (720p+2k) e ícone de ban."""
    problems: list[str] = []
    if base_dir is None:
        base_dir = Path(resource_path("assets/heroes"))

    missing_lineup: list[str] = []
    for role, heroes in HEROES_ROLES.items():
        folder = _ROLE_TO_FOLDER.get(role)
        if folder is None:
            continue
        for hero in heroes:
            key = normalize_hero_name(hero)
            for res in ("720p", "2k"):
                if not _has_template(base_dir / res / folder, key):
                    missing_lineup.append(f"{hero} ({res}/{folder})")
    if missing_lineup:
        problems.append(f"[templates] retratos de lineup AUSENTES: {', '.join(missing_lineup)}")

    bans_dir = base_dir / "bans"
    missing_bans = [
        h for h in get_all_heroes() if not _has_template(bans_dir, normalize_hero_name(h))
    ]
    if missing_bans:
        problems.append(f"[templates] ícones de BAN ausentes: {', '.join(missing_bans)}")
    return problems


def validate_all() -> list[str]:
    """Roda todas as validações e devolve a lista consolidada de problemas."""
    problems: list[str] = []
    try:
        # As colunas vêm do CABEÇALHO do CSV (e não da matriz normalizada): um
        # herói sem nenhum dado ainda tem coluna própria na planilha.
        problems += validate_matrix(
            datasource.get_ally_matrix(), "synergies", datasource.read_synergies_data().columns
        )
        problems += validate_matrix(
            datasource.get_enemy_matrix(), "counters", datasource.read_counters_data().columns
        )
    except Exception as e:  # noqa: BLE001
        problems.append(f"[matrizes] falha ao carregar: {e}")
    problems += validate_stats()
    problems += validate_templates()
    return problems


def report_problems(problems: list[str], echo=print) -> bool:
    """Imprime os problemas de forma clara. Devolve True se estiver tudo ok."""
    if not problems:
        echo("[validação] OK — matrizes, stats e templates consistentes.")
        return True
    echo("=" * 70)
    echo(f"[validação] {len(problems)} PROBLEMA(S) encontrado(s) nos dados:")
    for p in problems:
        echo(f"  - {p}")
    echo("=" * 70)
    return False
