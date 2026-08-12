"""Aceitação da nova Tank D.Mon (v1.2.14) — herói de primeira classe.

Cobre o caminho inteiro de uma hero nova: fonte de verdade (`HEROES_ROLES`),
normalização, templates de lineup nos dois bancos, presença nas matrizes com a
linha/coluna VAZIAS, stats com winrate 0 e o scoring rodando com ela dos dois
lados sem exceção e sem contribuição inventada.

Serve de gabarito para a próxima hero: se algum passo da adição for esquecido,
um destes testes cai.
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

HERO = "D.Mon"
KEY = "dmon"
ROLE = "TANK"
ASSETS = Path(resource_path("assets/heroes"))
TANK_2K_SIZE = (84, 80)  # padrão do banco 2K do lineup


def _repo_stats() -> pd.DataFrame:
    """stats_inputs.csv DO REPOSITÓRIO.

    `read_stats_inputs()` sem argumento prefere o override do usuário em
    %APPDATA% (que pode ser antigo e nem conhecer a hero nova) — aqui o alvo é o
    arquivo versionado, então o caminho é explícito.
    """
    return datasource.read_stats_inputs(resource_path(datasource.STATS_FILE))


def _matrices():
    return datasource.get_ally_matrix(), datasource.get_enemy_matrix()


def _reasons(score: dict) -> list[str]:
    """Lista de razões de `calculate_hero_score` (o dict é heterogêneo)."""
    reasons = score["reasons"]
    assert isinstance(reasons, list)
    return reasons


# ---------------------------------------------------------------------------
# Herói: fonte de verdade e normalização
# ---------------------------------------------------------------------------
def test_dmon_registrada_como_tank():
    assert HERO in heroes.HEROES_ROLES[ROLE]
    assert HERO in heroes.get_all_heroes()
    assert heroes.get_hero_role(HERO) == ROLE


def test_normalizacao_do_nome():
    # A normalização atual já dá conta: o ponto some, como em "D.Va" -> "dva".
    assert normalize_hero_name(HERO) == KEY
    assert normalize_hero_name("DMon") == KEY  # rótulo das planilhas/templates
    assert normalize_hero_name("d.mon") == KEY
    # Chave própria — não colide com nenhum outro herói (em especial a D.Va).
    keys = [normalize_hero_name(h) for h in heroes.get_all_heroes()]
    assert keys.count(KEY) == 1
    assert normalize_hero_name("D.Va") != KEY


def test_hero_from_name():
    hero = Hero.from_name(HERO)
    assert (hero.name, hero.key, hero.role) == (HERO, KEY, ROLE)


def test_pickrate_neutra_da_role_acompanha_o_novo_tank():
    """A pr neutra é derivada de HEROES_ROLES — nada de contagem fixa."""
    pr = heroes.get_role_neutral_pickrates()
    assert pr[ROLE] == pytest.approx(heroes.SLOTS[ROLE] / len(heroes.HEROES_ROLES[ROLE]))


# ---------------------------------------------------------------------------
# Templates do lineup (720p e 2K)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("banco", ["720p", "2k"])
def test_template_de_lineup_existe_nos_dois_bancos(banco):
    assert validation._has_template(ASSETS / banco / "tank", KEY), (
        f"nenhum template de {HERO} em assets/heroes/{banco}/tank"
    )


def test_template_2k_segue_o_padrao_dos_demais_tanks():
    """Mesmas dimensões e mesmo canal dos Tanks já existentes no banco 2K."""
    tank_2k = ASSETS / "2k" / "tank"
    dims, modes = set(), set()
    for p in tank_2k.iterdir():
        if normalize_hero_name(p.stem) == KEY:
            continue
        with Image.open(p) as im:
            dims.add(im.size)
            modes.add(im.mode)
    assert dims == {TANK_2K_SIZE} and modes == {"RGB"}, f"banco 2K heterogêneo: {dims} {modes}"

    meus = [p for p in tank_2k.iterdir() if normalize_hero_name(p.stem) == KEY]
    assert meus, "D.Mon ausente do banco 2K"
    for p in meus:
        with Image.open(p) as im:
            assert im.size == TANK_2K_SIZE, f"{p.name}: {im.size}"
            assert im.mode == "RGB", f"{p.name}: modo {im.mode}"


def test_template_720p_segue_o_canal_do_banco():
    """Os retratos 720p da D.Mon entraram no banco sem canal alfa, como os demais."""
    for p in (ASSETS / "720p" / "tank").iterdir():
        if normalize_hero_name(p.stem) != KEY:
            continue
        with Image.open(p) as im:
            assert im.mode == "RGB", f"{p.name}: modo {im.mode}"


@pytest.mark.parametrize(
    "full_w,banco_esperado",
    [(1280, "720p"), (1920, "2k"), (2560, "2k")],  # 720p / 1080p interpolado / 2K
)
def test_banco_escolhido_pela_resolucao_contem_dmon(full_w, banco_esperado):
    """O banco que o matching realmente carrega em cada resolução tem a D.Mon."""
    banco = resolution.template_bank_for_resolution(full_w)
    assert banco == banco_esperado
    crop_size, window_h = matching.compute_dims(resolution.resolution_scale(full_w))
    templates = matching.load_all_templates(
        matching.templates_base_dir / banco, (crop_size[0], window_h)
    )
    nomes = {normalize_hero_name(name) for name, _arr in templates["tank"]}
    assert KEY in nomes, f"[{full_w}px -> {banco}] D.Mon fora do banco carregado"


# ---------------------------------------------------------------------------
# Matrizes: presente, porém VAZIA (sem valores inventados)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "matriz,csv_reader",
    [
        (datasource.get_ally_matrix, datasource.read_synergies_data),
        (datasource.get_enemy_matrix, datasource.read_counters_data),
    ],
    ids=["synergies", "counters"],
)
def test_dmon_presente_e_vazia_nas_matrizes(matriz, csv_reader):
    m = matriz()
    df = csv_reader()

    # A LINHA existe (o herói está na matriz)...
    assert KEY in m, "D.Mon não está nas linhas da matriz"
    # ...e a COLUNA existe no cabeçalho do CSV de runtime.
    assert KEY in {normalize_hero_name(str(c)) for c in df.columns}

    # ...mas nenhuma célula tem valor: nem a linha dela...
    assert m[KEY] == {}, f"a linha de {HERO} tem valores: {m[KEY]}"
    # ...nem a coluna dela em nenhum outro herói.
    com_valor = [h for h, row in m.items() if KEY in row]
    assert com_valor == [], f"heróis com valor contra {HERO}: {com_valor}"


def test_matrizes_sem_linhas_ou_colunas_duplicadas():
    esperado = {normalize_hero_name(h) for h in heroes.get_all_heroes()}
    for reader in (datasource.read_synergies_data, datasource.read_counters_data):
        df = reader()
        idx = [normalize_hero_name(str(i)) for i in df.index]
        cols = [normalize_hero_name(str(c)) for c in df.columns]
        assert len(idx) == len(set(idx)) == len(esperado)
        assert len(cols) == len(set(cols)) == len(esperado)
        assert set(idx) == set(cols) == esperado


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def test_dmon_no_stats_inputs_com_winrate_zero():
    df = _repo_stats()
    minhas = df[df["hero"] == HERO]
    assert len(minhas) == len(heroes.get_map_names()), (
        f"{HERO} em {len(minhas)} mapas, esperado {len(heroes.get_map_names())}"
    )
    assert set(minhas["role"]) == {ROLE}
    assert [float(v) for v in minhas["winrate"]] == [0.0] * len(minhas), "winrate de D.Mon != 0"
    assert len(set(minhas["map"])) == len(minhas)  # um mapa por linha, sem duplicata


def test_meta_strength_de_dmon_e_praticamente_neutro():
    """Com pickrate 0 a confiança vai a ~0, então o winrate 0 NÃO vira uma
    penalidade artificial no MetaStrength da própria D.Mon."""
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    assert abs(meta.get(KEY, 0.0)) < 0.5, f"MetaStrength de {HERO} = {meta.get(KEY)}"


def test_stats_sem_dmon_nao_quebram_o_scoring():
    """Usuário com override de stats antigo (sem a hero nova): ela simplesmente
    fica sem MetaStrength — chave ausente vale 0.0, o ranking continua."""
    df = _repo_stats()
    antigo = df.loc[df["hero"] != HERO].copy()
    meta = scoring.load_meta_strength(antigo, "Ilios")  # pyright: ignore[reportArgumentType]
    assert KEY not in meta
    ally, enemy = _matrices()
    data = scoring.calculate_hero_score(HERO, ally, enemy, ["Mercy"], ["Tracer"], {}, meta)
    assert data["meta_score"] == 0.0
    assert data["total"] == 0.0


# ---------------------------------------------------------------------------
# Scoring — D.Mon aliada, inimiga e candidata
# ---------------------------------------------------------------------------
def test_dmon_como_inimiga_nao_quebra_e_nao_pontua():
    ally, enemy = _matrices()
    enemies, allies = [HERO, "Tracer"], ["Ana"]
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    w = scoring.compute_threat_weights(enemies, enemy, allies, meta, synergy_matrix=ally)
    # Sem counters e sem sinergia, o raw da D.Mon só carrega o termo de mapa
    # (≈0), então o multiplicador de ameaça fica praticamente neutro.
    assert w[KEY] == pytest.approx(scoring.NEUTRAL_WEIGHT, abs=0.05)

    data = scoring.calculate_hero_score("Winston", ally, enemy, allies, enemies, w, meta)
    so_dmon = scoring.calculate_hero_score("Winston", ally, enemy, allies, [HERO], w, meta)
    assert so_dmon["counter_score"] == 0.0  # nenhum counter inventado contra D.Mon
    assert all(HERO not in r for r in _reasons(data))


def test_dmon_como_aliada_nao_quebra_e_nao_pontua():
    ally, enemy = _matrices()
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    com = scoring.calculate_hero_score("Ana", ally, enemy, [HERO, "Tracer"], [], {}, meta)
    sem = scoring.calculate_hero_score("Ana", ally, enemy, ["Tracer"], [], {}, meta)
    assert com["synergy_score"] == sem["synergy_score"]  # D.Mon não soma nada
    assert all(HERO not in r for r in _reasons(com))


def test_dmon_como_candidata_pontua_zero_em_counter_e_sinergia():
    ally, enemy = _matrices()
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    enemies = ["Tracer", "Ana"]
    w = scoring.compute_threat_weights(enemies, enemy, ["Mercy"], meta, synergy_matrix=ally)
    data = scoring.calculate_hero_score(HERO, ally, enemy, ["Mercy"], enemies, w, meta)
    assert data["counter_score"] == 0.0
    assert data["synergy_score"] == 0.0
    assert data["total"] == data["meta_score"]


def test_ranking_completo_inclui_dmon_sem_excecao():
    ally, enemy = _matrices()
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    tanks = heroes.HEROES_ROLES[ROLE]
    enemies = ["Tracer", "Ana", "Winston"]
    w = scoring.compute_threat_weights(enemies, enemy, ["Mercy"], meta, synergy_matrix=ally)
    recs, _excluded = scoring.rank_heroes(
        tanks, ["Mercy"], enemies, ally, enemy, w, meta, mapa="Ilios"
    )
    assert HERO in [r.hero.name for r in recs]
    assert len(recs) == len(tanks)
