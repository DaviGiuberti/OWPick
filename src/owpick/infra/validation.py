"""validation.py — Validação das matrizes e dados na carga (tarefa 5.2).

Verifica, com AVISOS CLAROS do que está faltando/errado:

  - matrizes (synergies/counters): heróis das linhas E colunas == HEROES_ROLES
    (⊆ e ⊇, após normalização) — pega typos históricos (Illarri/Rroadhog) como
    linhas/colunas órfãs e heróis ausentes. As colunas são conferidas contra o
    CABEÇALHO do CSV, não contra os valores presentes: um herói ainda SEM dados
    (linha/coluna vazias) continua sendo uma coluna válida;
  - stats_inputs.csv: cobre os 30 mapas e as roles esperadas (DPS/TANK/SUP);
  - templates: todo herói tem retrato no lineup (720p E 2k, na role certa) e um
    ícone de ban em assets/heroes/bans/;
  - regras de dupla de DPS (data/dps_duo_rules.json): cada eixo cobre os DPS,
    cada tank tem exatamente uma regra, pares e trios só com classes conhecidas.

Cada função devolve uma lista de PROBLEMAS (strings legíveis). Lista vazia = ok.
Usado nos testes (rede da 1.3) e, opcionalmente, no boot em modo --debug.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from owpick.core.duo import parse_class_pair, parse_duo_rules
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

# A Flanker é declarada como subconjunto do Dano Médio: (eixo, classe).
FLANKER_PARENT = ("dano", "Médio")


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
    """Valida que stats_inputs.csv cobre os 30 mapas e as roles esperadas."""
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


def _role_keys(role: str) -> set[str]:
    return {normalize_hero_name(h) for h in HEROES_ROLES[role]}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_pairs(
    label: str, axis: str, pairs: Iterable[str], axis_classes: dict[str, set[str]]
) -> list[str]:
    """Pares 'A+B' de uma regra/trio: eixo existente e as duas classes nele.

    Só roda depois de `parse_duo_rules` aceitar a estrutura, então todo par já
    tem exatamente duas classes."""
    if axis not in axis_classes:
        return [f"[duo] {label}: eixo desconhecido '{axis}'"]
    problems: list[str] = []
    for pair in pairs:
        unknown = set(parse_class_pair(pair)) - axis_classes[axis]
        if unknown:
            problems.append(
                f"[duo] {label}: classe(s) fora do eixo '{axis}' em '{pair}': "
                f"{', '.join(sorted(unknown))}"
            )
    return problems


def validate_duo_rules(data: dict | None = None) -> list[str]:
    """Valida as regras de dupla de DPS (data/dps_duo_rules.json) contra HEROES_ROLES.

    - cada eixo cobre os DPS, cada um em UMA classe, sem herói inexistente ou de
      outra role (um DPS novo sem classe aparece aqui);
    - a Flanker é subconjunto da classe Médio do eixo "dano";
    - cada tank está em EXATAMENTE uma regra (um tank novo sem regra aparece
      aqui); pares só com classes do eixo da regra; valores numéricos;
    - trios: suporte é SUP, tanks são TANK, par com classes do eixo.

    `data=None` lê o arquivo do repositório/bundle.
    """
    if data is None:
        try:
            data = datasource.read_duo_rules_data()
        except Exception as e:  # noqa: BLE001
            return [f"[duo] não foi possível ler {datasource.DUO_RULES_FILE}: {e}"]
    try:
        parse_duo_rules(data)
    except Exception as e:  # noqa: BLE001
        return [f"[duo] estrutura inválida em {datasource.DUO_RULES_FILE}: {e!r}"]

    problems: list[str] = []
    dps, tanks, sups = _role_keys("DPS"), _role_keys("TANK"), _role_keys("SUP")

    axis_classes: dict[str, set[str]] = {}
    for axis, by_class in data["axes"].items():
        axis_classes[axis] = set(by_class)
        class_of: dict[str, str] = {}
        for cls, names in by_class.items():
            for name in names:
                key = normalize_hero_name(name)
                if key not in dps:
                    problems.append(
                        f"[duo] eixo '{axis}', classe '{cls}': '{name}' não é DPS de HEROES_ROLES"
                    )
                elif key in class_of:
                    problems.append(
                        f"[duo] eixo '{axis}': '{name}' em duas classes "
                        f"('{class_of[key]}' e '{cls}')"
                    )
                else:
                    class_of[key] = cls
        missing = dps - set(class_of)
        if missing:
            problems.append(f"[duo] eixo '{axis}': DPS SEM classe: {', '.join(sorted(missing))}")

    parent_axis, parent_class = FLANKER_PARENT
    parent = {
        normalize_hero_name(h) for h in data["axes"].get(parent_axis, {}).get(parent_class, [])
    }
    for name in data.get("flanker", []):
        key = normalize_hero_name(name)
        if key not in dps:
            problems.append(f"[duo] flanker: '{name}' não é DPS de HEROES_ROLES")
        elif key not in parent:
            problems.append(
                f"[duo] flanker: '{name}' fora da classe '{parent_class}' do eixo '{parent_axis}'"
            )

    rule_of: dict[str, str] = {}
    for rule in data["rules"]:
        label = f"regra '{rule['name']}'"
        problems += _check_pairs(label, rule["axis"], rule["pairs"], axis_classes)
        for pair, value in rule["pairs"].items():
            if not _is_number(value):
                problems.append(f"[duo] {label}: valor não numérico em '{pair}': {value!r}")
        for tank in rule["tanks"]:
            key = normalize_hero_name(tank)
            if key not in tanks:
                problems.append(f"[duo] {label}: '{tank}' não é TANK de HEROES_ROLES")
            elif key in rule_of:
                problems.append(
                    f"[duo] '{tank}' em duas regras ('{rule_of[key]}' e '{rule['name']}')"
                )
            else:
                rule_of[key] = rule["name"]
    missing_tanks = tanks - set(rule_of)
    if missing_tanks:
        problems.append(f"[duo] tanks SEM regra: {', '.join(sorted(missing_tanks))}")

    for trio in data.get("trios", []):
        label = f"trio com '{trio['support']}'"
        if normalize_hero_name(trio["support"]) not in sups:
            problems.append(f"[duo] {label}: '{trio['support']}' não é SUP de HEROES_ROLES")
        problems += _check_pairs(label, trio["axis"], [trio["pair"]], axis_classes)
        if not _is_number(trio["value"]):
            problems.append(f"[duo] {label}: valor não numérico: {trio['value']!r}")
        for tank in trio["tanks"]:
            if normalize_hero_name(tank) not in tanks:
                problems.append(f"[duo] {label}: '{tank}' não é TANK de HEROES_ROLES")
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
    problems += validate_duo_rules()
    return problems


def report_problems(problems: list[str], echo=print) -> bool:
    """Imprime os problemas de forma clara. Devolve True se estiver tudo ok."""
    if not problems:
        echo("[validação] OK — matrizes, stats, templates e regras de dupla consistentes.")
        return True
    echo("=" * 70)
    echo(f"[validação] {len(problems)} PROBLEMA(S) encontrado(s) nos dados:")
    for p in problems:
        echo(f"  - {p}")
    echo("=" * 70)
    return False
