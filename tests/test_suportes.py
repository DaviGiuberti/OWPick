"""Sinergias SUP x SUP por categoria de suporte e a Sombra como Suporte (v1.2.16).

As sinergias entre dois suportes em `data/heroes ally.xlsx` saem de uma
classificação em 3 categorias (ver DOCUMENTACAO.md, "Categorias de Suporte"),
com uma tabela SIMÉTRICA de valores. A v1.2.16 subiu Meio x Flex de 0 para +2
(nos dois sentidos), colocou o novo Doctrine em Flex (= Kiriko) e a Sombra — que
passou de DPS para Suporte no jogo — em Meio (= Mizuki).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from owpick import paths, settings
from owpick.core import heroes, scoring
from owpick.core.heroes import get_hero_role, normalize_hero_name
from owpick.infra import datasource, storage
from owpick.infra.resources import resource_path

FLEX = ["Ana", "Baptiste", "Doctrine", "Kiriko", "Moira"]
MAIN = ["Brigitte", "Jetpack Cat", "Lúcio", "Mercy", "Zenyatta"]
MEIO = ["Illari", "Juno", "Lifeweaver", "Mizuki", "Sombra", "Wuyang"]
TABLE = {
    ("flex", "flex"): -2,
    ("flex", "main"): 2,
    ("flex", "meio"): 2,
    ("main", "main"): -12,
    ("main", "meio"): -8,
    ("meio", "meio"): -4,
}
CATEGORY = {
    **{normalize_hero_name(h): "flex" for h in FLEX},
    **{normalize_hero_name(h): "main" for h in MAIN},
    **{normalize_hero_name(h): "meio" for h in MEIO},
}
SUP_KEYS = {normalize_hero_name(h) for h in heroes.HEROES_ROLES["SUP"]}
ASSETS = Path(resource_path("assets/heroes"))


def _y(cat_a: str, cat_b: str) -> int:
    return TABLE.get((cat_a, cat_b), TABLE.get((cat_b, cat_a), 0))


# ---------------------------------------------------------------------------
# Categorias de suporte
# ---------------------------------------------------------------------------
def test_categorias_cobrem_todos_os_suportes_sem_sobreposicao():
    assert len(FLEX) + len(MAIN) + len(MEIO) == len(SUP_KEYS)
    assert set(CATEGORY) == SUP_KEYS


def test_bloco_sup_x_sup_segue_a_tabela_de_categorias():
    """Os 16 x 16 pares da matriz de runtime batem com a tabela (diagonal = -11)."""
    ally = datasource.get_ally_matrix()
    erros = []
    for h in SUP_KEYS:
        for a in SUP_KEYS:
            esperado = -11 if h == a else _y(CATEGORY[h], CATEGORY[a])
            if ally[h].get(a) != esperado:
                erros.append((h, a, ally[h].get(a), esperado))
    assert erros == [], erros


@pytest.mark.parametrize("meio", MEIO)
@pytest.mark.parametrize("flex", FLEX)
def test_meio_x_flex_vale_2_nos_dois_sentidos(meio, flex):
    ally = datasource.get_ally_matrix()
    m, f = normalize_hero_name(meio), normalize_hero_name(flex)
    assert ally[m][f] == ally[f][m] == 2


# ---------------------------------------------------------------------------
# Sombra: DPS -> Suporte
# ---------------------------------------------------------------------------
def test_sombra_e_suporte():
    assert "Sombra" in heroes.HEROES_ROLES["SUP"]
    assert "Sombra" not in heroes.HEROES_ROLES["DPS"]
    assert get_hero_role("Sombra") == "SUP"


@pytest.mark.parametrize("banco", ["720p", "2k"])
def test_templates_da_sombra_na_pasta_de_suporte(banco):
    """O matching só compara cada slot com a pasta da role do slot: na pasta de
    DPS a Sombra nunca seria encontrada nos slots de suporte."""

    def nomes(role: str) -> set[str]:
        return {p.name for p in (ASSETS / banco / role).iterdir() if p.stem == "Sombra"}

    assert nomes("sup") == {"Sombra.png", "Sombra.jpg"}
    assert nomes("dps") == set()


def test_sinergia_da_sombra_com_suportes_igual_a_da_mizuki():
    ally = datasource.get_ally_matrix()
    for x in SUP_KEYS - {"sombra", "mizuki"}:
        assert ally["sombra"][x] == ally["mizuki"][x], x
        assert ally[x]["sombra"] == ally[x]["mizuki"], x
    # Entre as duas: Meio x Meio.
    assert ally["sombra"]["mizuki"] == ally["mizuki"]["sombra"] == -4


def test_resto_da_sombra_vazio_exceto_dmon():
    """O autor limpou a linha/coluna da Sombra (outro kit, dados antigos de DPS):
    só o bloco SUP x SUP e o cruzamento com a D.Mon (pesquisa) têm valor."""
    ally = datasource.get_ally_matrix()
    enemy = datasource.get_enemy_matrix()
    assert set(ally["sombra"]) == SUP_KEYS | {"dmon"}
    assert {h for h, row in ally.items() if "sombra" in row} == SUP_KEYS | {"dmon"}
    assert enemy["sombra"] == {"dmon": -1.0}
    assert {h: row["sombra"] for h, row in enemy.items() if "sombra" in row} == {"dmon": 1.0}


def test_stats_da_sombra_como_suporte_e_sem_dados():
    df = datasource.read_stats_inputs(resource_path(datasource.STATS_FILE))
    sombra = df[df["hero"] == "Sombra"]
    assert len(sombra) == len(heroes.get_map_names())
    assert set(sombra["role"]) == {"SUP"}
    # Os números antigos eram da Sombra DPS (outro kit): vazio = sem dado.
    assert all(pd.isna(v) for v in sombra["winrate"])


def test_par_mercy_sombra_usa_o_peso_de_sup_x_sup():
    """Mercy x Sombra deixou de ser Mercy x DPS (peso fixo 1): agora é SUP x SUP —
    no Counter-first, o beta_syn_sup_sup (0.65)."""
    ally = datasource.get_ally_matrix()
    w = scoring.resolve_weights("counter-first")
    data = scoring.calculate_hero_score("Mercy", ally, {}, ["Sombra"], [], {}, {}, weights=w)
    assert w.beta_syn_sup_sup is not None
    assert data["synergy_score"] == pytest.approx(ally["mercy"]["sombra"] * w.beta_syn_sup_sup)


# ---------------------------------------------------------------------------
# Favoritos: quem já tinha a Sombra como favorita (DPS.txt antigo)
# ---------------------------------------------------------------------------
@pytest.fixture
def user_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    paths.ensure_dirs()
    yield tmp_path
    settings.reload()


def _write(name: str, lines: list[str]) -> None:
    Path(paths.user_file(name)).write_text("\n".join(lines), encoding="utf-8")


def _read(name: str) -> list[str]:
    text = Path(paths.user_file(name)).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def test_favorito_que_mudou_de_role_vai_para_o_arquivo_novo(user_env):
    # Estado gravado pela v1.2.15: Sombra no DPS.txt.
    _write("ALL.txt", ["Tracer", "Sombra", "Ana"])
    _write("DPS.txt", ["Tracer", "Sombra"])
    _write("SUP.txt", ["Ana"])
    _write("TANK.txt", [])

    assert storage.sync_role_files(get_hero_role) is True
    assert storage.read_playable_heroes("DPS") == ["Tracer"]
    assert storage.read_playable_heroes("SUP") == ["Sombra", "Ana"]  # ordem do ALL.txt
    assert storage.load_favorites() == ["Tracer", "Sombra", "Ana"]  # ALL.txt intacto


def test_arquivos_ja_sincronizados_nao_sao_regravados(user_env):
    storage.save_heroes_to_files(["Tracer", "Sombra", "Ana"], get_hero_role)
    antes = {n: Path(paths.user_file(n)).stat().st_mtime_ns for n in ("DPS.txt", "SUP.txt")}
    assert storage.sync_role_files(get_hero_role) is False
    depois = {n: Path(paths.user_file(n)).stat().st_mtime_ns for n in ("DPS.txt", "SUP.txt")}
    assert antes == depois


def test_sem_favoritos_nao_toca_em_nada(user_env):
    assert storage.sync_role_files(get_hero_role) is False  # sem ALL.txt
    assert not Path(paths.user_file("DPS.txt")).exists()

    _write("ALL.txt", [])  # vazio: regravar apagaria os arquivos por role
    _write("DPS.txt", ["Tracer"])
    assert storage.sync_role_files(get_hero_role) is False
    assert _read("DPS.txt") == ["Tracer"]


def test_arquivo_de_role_corrompido_e_regenerado(user_env):
    _write("ALL.txt", ["Tracer", "Sombra"])
    Path(paths.user_file("DPS.txt")).write_bytes(b"\xff\xfe\x00lixo")
    assert storage.sync_role_files(get_hero_role) is True
    assert _read("DPS.txt") == ["Tracer"]
    assert _read("SUP.txt") == ["Sombra"]
