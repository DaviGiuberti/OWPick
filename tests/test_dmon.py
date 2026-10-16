"""Aceitação da Tank D.Mon — herói de primeira classe.

v1.2.14: entrou com a linha/coluna VAZIAS nas matrizes e winrate 0.
v1.2.16: as duas matrizes foram preenchidas por pesquisa (counter rating do
counterwatch.gg na Season 5, convertido com limiares calibrados contra os tanques
já preenchidos; sinergias por evidência de duplas + guias, com base nos tanques
de perfil mais próximo) e o ícone de ban foi gerado do retrato oficial. A
metodologia está em DOCUMENTACAO.md ("Tabela da D.Mon").

Cobre o caminho inteiro de uma hero nova: fonte de verdade (`HEROES_ROLES`),
normalização, templates de lineup nos dois bancos, ícone de ban, matrizes, stats
com winrate 0 e o scoring rodando com ela dos dois lados. Serve de gabarito para
a próxima hero: se algum passo da adição for esquecido, um destes testes cai.
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
BAN_SIZE = (128, 128)  # padrão do banco de bans


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


def _k(name: str) -> str:
    return normalize_hero_name(name)


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
# Templates do lineup (720p e 2K) e ícone de ban
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


def test_icone_de_ban_existe_e_segue_o_padrao():
    """v1.2.16 fechou a lacuna da v1.2.14: o ícone 3D oficial está no banco de bans,
    no mesmo formato dos demais (128x128 RGB), e o matching de bans o carrega."""
    p = ASSETS / "bans" / "DMon.png"
    assert p.exists(), "ícone de ban da D.Mon ausente"
    with Image.open(p) as im:
        assert (im.size, im.mode) == (BAN_SIZE, "RGB")
    templates = matching.load_ban_templates(
        matching.templates_base_dir / matching.BAN_TEMPLATES_DIR_NAME, matching.BAN_COMPARE_SIZE
    )
    assert KEY in {normalize_hero_name(name) for name, _arr in templates}


# ---------------------------------------------------------------------------
# Matrizes: completas, na escala e ancoradas na pesquisa (v1.2.16)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "matriz,csv_reader",
    [
        (datasource.get_ally_matrix, datasource.read_synergies_data),
        (datasource.get_enemy_matrix, datasource.read_counters_data),
    ],
    ids=["synergies", "counters"],
)
def test_dmon_completa_nas_matrizes(matriz, csv_reader):
    """Linha e coluna da D.Mon têm valor contra TODOS os heróis (nenhuma célula
    vazia) e ficam dentro da escala da matriz (-2..+2 fora da diagonal)."""
    m = matriz()
    df = csv_reader()
    todos = {normalize_hero_name(h) for h in heroes.get_all_heroes()}

    assert KEY in {normalize_hero_name(str(c)) for c in df.columns}
    assert set(m[KEY]) == todos, f"linha de {HERO} incompleta: faltam {todos - set(m[KEY])}"
    sem_valor = [h for h, row in m.items() if KEY not in row]
    assert sem_valor == [], f"heróis sem valor contra {HERO}: {sem_valor}"

    fora = {
        (a, b, v)
        for a, b, v in [(KEY, x, m[KEY][x]) for x in todos] + [(x, KEY, m[x][KEY]) for x in todos]
        if a != b and not -2 <= v <= 2
    }
    assert fora == set(), f"valores fora da escala: {fora}"


def test_counters_da_dmon_sao_antissimetricos():
    """C(D.Mon, X) = -C(X, D.Mon) para todo X (a convenção de ~94% da matriz); o
    espelho D.Mon x D.Mon é neutro."""
    _ally, enemy = _matrices()
    for x in enemy:
        if x == KEY:
            continue
        assert enemy[KEY][x] == -enemy[x][KEY], f"{x}: {enemy[KEY][x]} vs {enemy[x][KEY]}"
    assert enemy[KEY][KEY] == 0


@pytest.mark.parametrize(
    "heroi,valor",
    [
        # Os dois counters mais fortes do dado (rating +24.2 e +23.2).
        ("Torbjörn", 2),
        ("Illari", 2),
        # Quem voa ou tem mobilidade vertical escapa do sabre (ela não tem lift).
        ("Pharah", 1),
        ("Freja", 1),
        ("Jetpack Cat", 1),
        # Quem a D.Mon mais pune: alvos frágeis sem defesa instantânea.
        ("Mercy", -1),
        ("Kiriko", -1),
        ("Lifeweaver", -1),
        ("Widowmaker", -1),
        ("Anran", -1),
        # Abaixo do limiar calibrado (|rating| < 3.0) = neutro.
        ("Reinhardt", 0),
        ("Doctrine", 0),
    ],
)
def test_counters_ancorados_na_pesquisa(heroi, valor):
    """C(X, D.Mon) = quanto X countera a D.Mon (positivo = X leva vantagem)."""
    _ally, enemy = _matrices()
    assert enemy[_k(heroi)][KEY] == valor


@pytest.mark.parametrize(
    "heroi,valor",
    [
        # Evidência forte (dado de dupla + guias): speed boost e quem segue o dash.
        ("Lúcio", 2),
        ("Juno", 2),
        ("Tracer", 2),
        ("Echo", 2),
        ("Shion", 2),
        # Poke que "a deixa sozinha na linha de frente" / piores parceiros.
        ("Ashe", -1),
        ("Pharah", -1),
        ("Widowmaker", -1),
        ("Junkrat", -1),
        ("Jetpack Cat", -1),
    ],
)
def test_sinergias_ancoradas_na_pesquisa(heroi, valor):
    """Com evidência específica da D.Mon, o valor vale nos dois sentidos."""
    ally, _enemy = _matrices()
    assert ally[KEY][_k(heroi)] == valor
    assert ally[_k(heroi)][KEY] == valor


def test_diagonal_da_sinergia_segue_a_convencao():
    ally, _enemy = _matrices()
    assert ally[KEY][KEY] == -11


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
    total = float(data["counter_score"]) + float(data["synergy_score"])  # pyright: ignore[reportArgumentType]
    assert data["total"] == pytest.approx(total)


# ---------------------------------------------------------------------------
# Scoring — D.Mon aliada, inimiga e candidata
# ---------------------------------------------------------------------------
def test_dmon_como_inimiga_pesa_pelos_counters():
    """D.Mon inimiga contra um time que ela countera vira AMEAÇA (w > 1), e quem a
    countera pontua por isso."""
    ally, enemy = _matrices()
    enemies, allies = [HERO, "Tracer"], ["Mercy", "Kiriko"]  # D.Mon countera as duas
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    w = scoring.compute_threat_weights(enemies, enemy, allies, meta, synergy_matrix=ally)
    assert w[KEY] > scoring.NEUTRAL_WEIGHT

    data = scoring.calculate_hero_score("Torbjörn", ally, enemy, allies, [HERO], w, meta)
    assert data["counter_score"] == pytest.approx(2 * w[KEY])  # C(Torbjörn, D.Mon) = 2
    assert any(r.startswith(f"countera {HERO}") for r in _reasons(data))


def test_dmon_como_aliada_soma_sinergia():
    ally, enemy = _matrices()
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    beta = scoring.DEFAULT_WEIGHTS.beta_syn  # SUP/DPS x TANK usa o β_syn do preset
    for candidato, y in (("Lúcio", 2), ("Ashe", -1)):
        com = scoring.calculate_hero_score(candidato, ally, enemy, [HERO, "Ana"], [], {}, meta)
        sem = scoring.calculate_hero_score(candidato, ally, enemy, ["Ana"], [], {}, meta)
        delta = float(com["synergy_score"]) - float(sem["synergy_score"])  # pyright: ignore[reportArgumentType]
        assert delta == pytest.approx(y * beta), candidato
        assert any(HERO in r for r in _reasons(com)), candidato


def test_dmon_como_candidata_pontua_counter_e_sinergia():
    ally, enemy = _matrices()
    meta = scoring.load_meta_strength(_repo_stats(), "Ilios")
    enemies = ["Mercy", "Kiriko"]  # C(D.Mon, ·) = +1 nas duas
    w = scoring.compute_threat_weights(enemies, enemy, ["Lúcio"], meta, synergy_matrix=ally)
    data = scoring.calculate_hero_score(HERO, ally, enemy, ["Lúcio"], enemies, w, meta)
    assert data["counter_score"] == pytest.approx(w["mercy"] + w["kiriko"])
    assert data["synergy_score"] == pytest.approx(2 * scoring.DEFAULT_WEIGHTS.beta_syn)
    soma = sum(float(data[k]) for k in ("meta_score", "counter_score", "synergy_score"))  # pyright: ignore[reportArgumentType]
    assert data["total"] == pytest.approx(soma)


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
