"""Aceitação do novo Suporte Doctrine (v1.2.16) — herói de primeira classe.

Segue o gabarito da D.Mon (tests/test_dmon.py): fonte de verdade, normalização,
templates de lineup nos dois bancos, ícone de ban, matrizes, stats e o scoring
rodando com ele dos dois lados.

Os dados que ainda não existem ficam VAZIOS (decisão do autor): nas matrizes só o
bloco SUP x SUP das sinergias (= Kiriko, categoria Flex — ver tests/test_suportes.py)
e o cruzamento com a D.Mon (pesquisa da v1.2.16) têm valor; nas stats, winrate e
pickrate vazios nos 30 mapas.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

from owpick.core import heroes, resolution, scoring
from owpick.core.heroes import normalize_hero_name
from owpick.core.models import Hero
from owpick.infra import datasource, matching, validation
from owpick.infra.resources import resource_path

HERO = "Doctrine"
KEY = "doctrine"
ROLE = "SUP"
ASSETS = Path(resource_path("assets/heroes"))
SUP_720P_SIZE = (41, 41)  # formato nativo do banco 720p de suportes
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def _repo_stats() -> pd.DataFrame:
    """stats_inputs.csv DO REPOSITÓRIO (não o override do usuário em %APPDATA%)."""
    return datasource.read_stats_inputs(resource_path(datasource.STATS_FILE))


def _matrices():
    return datasource.get_ally_matrix(), datasource.get_enemy_matrix()


def _keys(role: str) -> set[str]:
    return {normalize_hero_name(h) for h in heroes.HEROES_ROLES[role]}


# ---------------------------------------------------------------------------
# Herói: fonte de verdade e normalização
# ---------------------------------------------------------------------------
def test_doctrine_registrado_como_suporte():
    assert HERO in heroes.HEROES_ROLES[ROLE]
    assert heroes.get_hero_role(HERO) == ROLE
    assert heroes.HEROES_ROLES[ROLE] == sorted(heroes.HEROES_ROLES[ROLE])  # ordem alfabética


def test_normalizacao_do_nome_e_chave_unica():
    assert normalize_hero_name(HERO) == KEY
    keys = [normalize_hero_name(h) for h in heroes.get_all_heroes()]
    assert keys.count(KEY) == 1


def test_hero_from_name():
    hero = Hero.from_name(HERO)
    assert (hero.name, hero.key, hero.role) == (HERO, KEY, ROLE)


def test_pickrate_neutra_do_suporte_acompanha_a_contagem():
    pr = heroes.get_role_neutral_pickrates()
    assert pr[ROLE] == pytest.approx(heroes.SLOTS[ROLE] / len(heroes.HEROES_ROLES[ROLE]))


# ---------------------------------------------------------------------------
# Templates do lineup e ícone de ban
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("banco", ["720p", "2k"])
def test_templates_nos_dois_bancos_em_rgb(banco):
    """Os dois recortes (`.png` fundo azul / `.jpg` fundo vermelho), sem alfa."""
    meus = sorted(
        p.name for p in (ASSETS / banco / "sup").iterdir() if normalize_hero_name(p.stem) == KEY
    )
    assert meus == ["Doctrine.jpg", "Doctrine.png"], meus
    for name in meus:
        with Image.open(ASSETS / banco / "sup" / name) as im:
            assert im.mode == "RGB", f"{banco}/{name}: modo {im.mode}"
            assert im.format == "PNG"  # a extensão .jpg do banco é histórica


def test_template_720p_no_formato_nativo_do_banco():
    """No 720p o retrato entra reduzido (LANCZOS) ao tamanho nativo do banco: um
    template 2K usado direto fica bem menos parecido com uma captura 720p real."""
    for name in ("Doctrine.png", "Doctrine.jpg"):
        with Image.open(ASSETS / "720p" / "sup" / name) as im:
            assert im.size == SUP_720P_SIZE, f"{name}: {im.size}"


def test_nenhum_template_com_nome_orfao():
    """Todo arquivo de imagem dos bancos resolve para um herói conhecido: um nome
    como `Doctrine.jpg.png` (stem `doctrine-jpg`) viraria um herói inexistente."""
    validos = {normalize_hero_name(h) for h in heroes.get_all_heroes()}
    orfaos = [
        str(p.relative_to(ASSETS))
        for p in ASSETS.rglob("*")
        if p.suffix.lower() in _IMAGE_SUFFIXES and normalize_hero_name(p.stem) not in validos
    ]
    assert orfaos == [], f"templates órfãos: {orfaos}"


@pytest.mark.parametrize("full_w", [1280, 1920, 2560])
def test_banco_carregado_em_cada_resolucao_contem_doctrine(full_w):
    banco = resolution.template_bank_for_resolution(full_w)
    crop_size, window_h = matching.compute_dims(resolution.resolution_scale(full_w))
    templates = matching.load_all_templates(
        matching.templates_base_dir / banco, (crop_size[0], window_h)
    )
    nomes = {normalize_hero_name(name) for name, _arr in templates["sup"]}
    assert KEY in nomes, f"[{full_w}px -> {banco}] Doctrine fora do banco de suportes"
    assert KEY not in {normalize_hero_name(n) for n, _ in templates["dps"] + templates["tank"]}


def test_icone_de_ban():
    p = ASSETS / "bans" / "Doctrine.png"
    with Image.open(p) as im:
        assert (im.size, im.mode) == ((128, 128), "RGB")
    assert validation._has_template(ASSETS / "bans", KEY)


# ---------------------------------------------------------------------------
# Matrizes: SUP x SUP como a Kiriko; o resto vazio (exceto a D.Mon)
# ---------------------------------------------------------------------------
def test_presente_nos_cabecalhos_das_duas_matrizes():
    for reader in (datasource.read_synergies_data, datasource.read_counters_data):
        df = reader()
        assert KEY in {normalize_hero_name(str(i)) for i in df.index}
        assert KEY in {normalize_hero_name(str(c)) for c in df.columns}


def test_sinergia_com_suportes_igual_a_da_kiriko():
    """Y(Doctrine, X) = Y(Kiriko, X) e Y(X, Doctrine) = Y(X, Kiriko) para todo outro
    suporte X; entre os dois Flex Sup o par vale -2."""
    ally, _enemy = _matrices()
    kiriko = "kiriko"
    for x in _keys("SUP") - {KEY, kiriko}:
        assert ally[KEY][x] == ally[kiriko][x], x
        assert ally[x][KEY] == ally[x][kiriko], x
    assert ally[KEY][kiriko] == ally[kiriko][KEY] == -2
    assert ally[KEY][KEY] == ally[kiriko][kiriko] == -11


def test_resto_das_matrizes_vazio_exceto_dmon():
    """Sem dado inventado: fora do bloco SUP x SUP (sinergias), a única célula com
    valor é o cruzamento com a D.Mon, preenchido pela pesquisa dela."""
    ally, enemy = _matrices()
    assert set(ally[KEY]) == _keys("SUP") | {"dmon"}
    assert {h for h, row in ally.items() if KEY in row} == _keys("SUP") | {"dmon"}
    assert enemy[KEY] == {"dmon": 0.0}
    assert {h for h, row in enemy.items() if KEY in row} == {"dmon"}


# ---------------------------------------------------------------------------
# Stats: presente nos 30 mapas, sem dados
# ---------------------------------------------------------------------------
def test_stats_vazias_nos_29_mapas():
    df = _repo_stats()
    meus = df[df["hero"] == HERO]
    assert len(meus) == len(heroes.get_map_names())
    assert set(meus["role"]) == {ROLE}
    assert all(pd.isna(v) for v in meus["winrate"])
    assert all(pd.isna(v) for v in meus["pickrate"])


def test_stats_vazias_nao_mexem_na_regua_dos_suportes():
    """Célula vazia = ausência de dado: o Doctrine não ganha MetaStrength e a
    média/desvio dos suportes fica idêntica à de um CSV sem as linhas dele (ao
    contrário do winrate 0, que comprimiria o z-score da role)."""
    df = _repo_stats()
    for mapa in ("Ilios", "Route 66", "Busan"):
        com = scoring.load_meta_strength(df, mapa)
        sem = scoring.load_meta_strength(df[df["hero"] != HERO], mapa)  # pyright: ignore[reportArgumentType]
        assert KEY not in com
        assert com == sem


# ---------------------------------------------------------------------------
# Scoring — aliado, inimigo e candidato
# ---------------------------------------------------------------------------
def test_scoring_com_doctrine_dos_dois_lados():
    ally, enemy = _matrices()
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    enemies = [HERO, "Tracer", "Winston"]
    w = scoring.compute_threat_weights(enemies, enemy, ["Mercy"], meta, synergy_matrix=ally)
    assert KEY in w

    # Candidato com Lúcio aliado (Flex x Main = +2, β do par SUP x SUP).
    data = scoring.calculate_hero_score(HERO, ally, enemy, ["Lúcio"], enemies, w, meta)
    beta = scoring.DEFAULT_WEIGHTS.beta_syn
    assert data["synergy_score"] == pytest.approx(2 * beta)
    assert data["counter_score"] == 0.0  # sem counters conhecidos

    sups = heroes.HEROES_ROLES[ROLE]
    recs, _excluded = scoring.rank_heroes(sups, ["Lúcio"], enemies, ally, enemy, w, meta)
    assert HERO in [r.hero.name for r in recs]
