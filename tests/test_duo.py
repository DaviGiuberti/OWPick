"""Regra de dupla de DPS por tank inimigo — coluna DUO (v1.2.17).

Substitui a sinergia DPS x DPS por categoria (v1.2.12–v1.2.16). Classes, regras e
valores vivem em data/dps_duo_rules.json (ver DOCUMENTACAO.md, "Classes de DPS e
regras por tank"); a lógica é core/duo.py, e o scoring soma o resultado numa
coluna própria (ranking) e num 4º termo do raw do tank inimigo (Enemy Threat).
"""

from __future__ import annotations

import copy

import pytest

from owpick import settings
from owpick.core import heroes, scoring
from owpick.core.duo import (
    EMPTY_DUO_RULES,
    DuoRules,
    class_pair,
    duo_terms,
    duo_threat_value,
    parse_class_pair,
    parse_duo_rules,
)
from owpick.core.heroes import normalize_hero_name
from owpick.infra import datasource, validation

RULES = datasource.load_duo_rules()
DATA = datasource.read_duo_rules_data()

# As listas exatamente como definidas pelo autor (v1.2.17).
FORTE = [
    "Ashe",
    "Bastion",
    "Cassidy",
    "Emre",
    "Hanzo",
    "Junkrat",
    "Reaper",
    "Sierra",
    "Sojourn",
    "Soldier: 76",
    "Symmetra",
    "Torbjörn",
]
MEDIO = [
    "Anran",
    "Echo",
    "Freja",
    "Genji",
    "Mei",
    "Pharah",
    "Shion",
    "Tracer",
    "Vendetta",
    "Venture",
    "Widowmaker",
]
FLANKER = ["Anran", "Genji", "Shion", "Tracer", "Vendetta", "Venture"]
HITSCAN = ["Ashe", "Bastion", "Cassidy", "Emre", "Sierra", "Sojourn", "Soldier: 76", "Widowmaker"]
FLEX = ["Anran", "Echo", "Genji", "Hanzo", "Junkrat", "Mei", "Pharah", "Vendetta", "Venture"]
OS_DOIS = ["Freja", "Reaper", "Shion", "Symmetra", "Torbjörn", "Tracer"]
RUIM_CONTRA_FORTE = [
    "D.Mon",
    "Mauga",
    "Orisa",
    "Ramattra",
    "Reinhardt",
    "Roadhog",
    "Winston",
    "Zarya",
]
RUIM_CONTRA_MISTA = ["D.Va", "Domina", "Doomfist", "Hazard", "Junker Queen", "Wrecking Ball"]
PRESETS = ["equilibrado", "counter-first", "meta-first", "conforto+"]


def _keys(names: list[str]) -> set[str]:
    return {normalize_hero_name(n) for n in names}


def _members(axis: str, cls: str) -> set[str]:
    return {k for k, c in RULES.classes[axis].items() if c == cls}


def _duo(candidate: str, allies: list[str], enemies: list[str], role: str | None = "DPS") -> float:
    return sum(v for v, _ in duo_terms(candidate, allies, enemies, role, RULES))


# ---------------------------------------------------------------------------
# Dados: data/dps_duo_rules.json exatamente como definido
# ---------------------------------------------------------------------------
def test_eixo_dano_forte_e_medio():
    assert _members("dano", "Forte") == _keys(FORTE)
    assert _members("dano", "Médio") == _keys(MEDIO)


def test_eixo_estilo_hitscan_flex_e_os_dois():
    assert _members("estilo", "Hitscan") == _keys(HITSCAN)
    assert _members("estilo", "Flex") == _keys(FLEX)  # Hanzo é Flex
    assert _members("estilo", "Os dois") == _keys(OS_DOIS)


@pytest.mark.parametrize("axis", ["dano", "estilo"])
def test_cada_eixo_cobre_os_23_dps(axis):
    assert set(RULES.classes[axis]) == _keys(heroes.HEROES_ROLES["DPS"])


def test_flanker_registrada_dentro_do_dano_medio():
    assert RULES.flanker == _keys(FLANKER)
    assert RULES.flanker <= _members("dano", "Médio")


def test_regras_por_tank():
    by_name = {r.name: r for r in RULES.rules}
    forte = by_name["ruim contra dupla de Dano Forte"]
    assert forte.axis == "dano" and forte.tanks == _keys(RUIM_CONTRA_FORTE)
    assert forte.pairs == {("Forte", "Forte"): 2, ("Forte", "Médio"): 0, ("Médio", "Médio"): -2}

    mista = by_name["ruim contra dupla mista"]
    assert mista.axis == "estilo" and mista.tanks == _keys(RUIM_CONTRA_MISTA)
    assert mista.pairs == {
        class_pair("Hitscan", "Flex"): 2,
        class_pair("Hitscan", "Os dois"): 2,
        class_pair("Flex", "Os dois"): 2,
        class_pair("Os dois", "Os dois"): 2,
        class_pair("Hitscan", "Hitscan"): -2,
        class_pair("Flex", "Flex"): -2,
    }

    sigma = by_name["forte contra dupla de Hitscan"]
    assert sigma.axis == "estilo" and sigma.tanks == {"sigma"}
    assert sigma.pairs == {("Hitscan", "Hitscan"): -2}


def test_cada_tank_tem_exatamente_uma_regra():
    for tank in heroes.HEROES_ROLES["TANK"]:
        key = normalize_hero_name(tank)
        assert sum(key in r.tanks for r in RULES.rules) == 1, tank


def test_trio_da_zenyatta_vale_contra_os_8_tanks_incluindo_dmon():
    (trio,) = RULES.trios
    assert trio.support_key == "zenyatta"
    assert (trio.axis, trio.pair, trio.value) == ("dano", ("Forte", "Forte"), 2)
    assert trio.tanks == _keys(RUIM_CONTRA_FORTE)
    assert "dmon" in trio.tanks


def test_par_de_classes_nao_tem_ordem():
    assert class_pair("Médio", "Forte") == class_pair("Forte", "Médio")
    assert parse_class_pair("Os dois+Hitscan") == parse_class_pair("Hitscan+Os dois")
    for invalido in ("Forte", "Forte+Médio+Forte", "Forte+"):
        with pytest.raises(ValueError):
            parse_class_pair(invalido)


# ---------------------------------------------------------------------------
# Validador: dados reais limpos, casos sintéticos acusados
# ---------------------------------------------------------------------------
def test_dados_reais_passam_no_validador():
    assert validation.validate_duo_rules() == []


def _rule(data: dict, name: str) -> dict:
    return next(r for r in data["rules"] if r["name"] == name)


@pytest.mark.parametrize(
    ("mutate", "trecho"),
    [
        (lambda d: d["axes"]["estilo"]["Os dois"].remove("Tracer"), "DPS SEM classe: tracer"),
        (lambda d: d["axes"]["estilo"]["Hitscan"].append("Tracer"), "em duas classes"),
        (lambda d: d["axes"]["dano"]["Forte"].append("Ana"), "'Ana' não é DPS"),
        (lambda d: d["flanker"].append("Ashe"), "flanker: 'Ashe' fora da classe 'Médio'"),
        (lambda d: d["flanker"].append("Ana"), "flanker: 'Ana' não é DPS"),
        (
            lambda d: _rule(d, "forte contra dupla de Hitscan")["tanks"].remove("Sigma"),
            "tanks SEM regra: sigma",
        ),
        (
            lambda d: _rule(d, "ruim contra dupla mista")["tanks"].append("Sigma"),
            "'Sigma' em duas regras",
        ),
        (
            lambda d: _rule(d, "ruim contra dupla mista")["tanks"].append("Ashe"),
            "'Ashe' não é TANK",
        ),
        (
            lambda d: _rule(d, "ruim contra dupla de Dano Forte")["pairs"].update(
                {"Forte+Hitscan": 2}
            ),
            "fora do eixo 'dano'",
        ),
        (
            lambda d: _rule(d, "ruim contra dupla mista").update(axis="potência"),
            "eixo desconhecido 'potência'",
        ),
        (
            lambda d: _rule(d, "ruim contra dupla mista")["pairs"].update({"Flex+Flex": "-2"}),
            "valor não numérico",
        ),
        (lambda d: d["trios"][0].update(support="Ashe"), "'Ashe' não é SUP"),
        (lambda d: d["trios"][0]["tanks"].append("Ana"), "'Ana' não é TANK"),
        (lambda d: d.pop("rules"), "estrutura inválida"),
        (
            lambda d: _rule(d, "ruim contra dupla mista")["pairs"].update({"Flex": 2}),
            "estrutura inválida",
        ),
    ],
)
def test_validador_acusa_cada_problema(mutate, trecho):
    data = copy.deepcopy(DATA)
    mutate(data)
    problems = validation.validate_duo_rules(data)
    assert any(trecho in p for p in problems), problems


def test_falha_ao_ler_as_regras_degrada_para_regras_vazias(monkeypatch, capsys):
    """Arquivo ausente/quebrado no bundle: aviso e ranking sem a coluna DUO."""

    def _quebrado(*_args, **_kwargs):
        raise FileNotFoundError("sumiu")

    monkeypatch.setattr(datasource, "read_duo_rules_data", _quebrado)
    datasource.load_duo_rules.cache_clear()
    try:
        assert datasource.load_duo_rules() is EMPTY_DUO_RULES
        assert "AVISO" in capsys.readouterr().out
    finally:
        datasource.load_duo_rules.cache_clear()


# ---------------------------------------------------------------------------
# Ranking jogando de DPS: dupla = candidato + o único DPS aliado
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tank", RUIM_CONTRA_FORTE)
def test_tank_ruim_contra_dupla_forte(tank):
    assert _duo("Ashe", ["Cassidy"], [tank]) == 2  # Forte+Forte sobe
    assert _duo("Genji", ["Cassidy"], [tank]) == 0  # Forte+Médio neutra
    assert _duo("Genji", ["Tracer"], [tank]) == -2  # Médio+Médio desce


@pytest.mark.parametrize("tank", RUIM_CONTRA_MISTA)
def test_tank_ruim_contra_dupla_mista(tank):
    assert _duo("Genji", ["Ashe"], [tank]) == 2  # Flex+Hitscan
    assert _duo("Widowmaker", ["Hanzo"], [tank]) == 2  # Hanzo é Flex
    assert _duo("Cassidy", ["Ashe"], [tank]) == -2  # Hitscan+Hitscan
    assert _duo("Genji", ["Mei"], [tank]) == -2  # Flex+Flex


@pytest.mark.parametrize("parceiro", ["Ashe", "Genji", "Tracer"])
def test_os_dois_sao_coringa_na_mista(parceiro):
    """'Os dois' + Hitscan, + Flex ou + outro 'Os dois' = mista: sempre sobe."""
    assert _duo("Reaper", [parceiro], ["D.Va"]) == 2


def test_sigma_so_pune_hitscan_mais_hitscan():
    assert _duo("Ashe", ["Soldier: 76"], ["Sigma"]) == -2
    assert _duo("Hanzo", ["Soldier: 76"], ["Sigma"]) == 0  # Hanzo é Flex
    assert _duo("Reaper", ["Soldier: 76"], ["Sigma"]) == 0  # 'Os dois' não é Hitscan aqui
    assert _duo("Genji", ["Mei"], ["Sigma"]) == 0  # as outras duplas são neutras


@pytest.mark.parametrize("role", ["ALL", "TANK", None])
def test_fora_da_role_dps_a_dupla_nao_se_aplica(role):
    assert duo_terms("Ashe", ["Cassidy"], ["Mauga"], role, RULES) == []


@pytest.mark.parametrize(
    ("allies", "enemies"),
    [
        ([], ["Mauga"]),  # sem DPS aliado identificado
        (["Reinhardt", "Ana"], ["Mauga"]),  # aliados sem DPS
        (["Cassidy", "Sojourn"], ["Mauga"]),  # 2 DPS aliados (modo sim)
        (["Cassidy"], []),  # tank inimigo não identificado
        (["Cassidy"], ["Tracer", "Ana"]),  # inimigos sem tank
        (["Cassidy"], ["Mauga", "Reinhardt"]),  # 2 tanks inimigos (modo sim)
    ],
)
def test_fora_do_formato_1_para_1_e_neutra(allies, enemies):
    assert duo_terms("Ashe", allies, enemies, "DPS", RULES) == []


def test_candidato_que_nao_e_dps_ou_sem_classe_e_neutro():
    assert duo_terms("Ana", ["Cassidy"], ["Mauga"], "DPS", RULES) == []
    sem_ashe = copy.deepcopy(DATA)
    sem_ashe["axes"]["dano"]["Forte"].remove("Ashe")
    rules = parse_duo_rules(sem_ashe)
    assert duo_terms("Ashe", ["Cassidy"], ["Mauga"], "DPS", rules) == []


def test_slots_vazios_nao_contam():
    assert _duo("Ashe", ["", "Cassidy", ""], ["", "Mauga"]) == 2


# ---------------------------------------------------------------------------
# Trio da Zenyatta: o bônus vai para quem completa o trio
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tank", RUIM_CONTRA_FORTE)
def test_trio_jogando_de_dps_soma_com_a_dupla(tank):
    allies = ["Reinhardt", "Cassidy", "Zenyatta", "Ana"]
    assert _duo("Ashe", allies, [tank]) == 2 + 2


def test_trio_exige_forte_forte_zen_aliada_e_tank_da_lista():
    zen = ["Cassidy", "Zenyatta"]
    assert _duo("Genji", zen, ["Mauga"]) == 0  # Médio+Forte: nem dupla nem trio
    assert _duo("Ashe", ["Cassidy", "Ana"], ["Mauga"]) == 2  # sem Zen: só a dupla
    assert _duo("Ashe", zen, ["D.Va"]) == -2  # D.Va fora do trio: só Hitscan+Hitscan


def test_trio_jogando_de_sup_vai_para_a_zen_candidata():
    allies = ["Reinhardt", "Cassidy", "Ashe", "Ana"]
    assert _duo("Zenyatta", allies, ["Mauga"], role="SUP") == 2
    assert _duo("Zenyatta", allies, ["D.Mon"], role="SUP") == 2
    assert _duo("Zenyatta", allies, ["D.Va"], role="SUP") == 0  # fora da lista do trio
    assert _duo("Zenyatta", ["Reinhardt", "Cassidy", "Genji", "Ana"], ["Mauga"], "SUP") == 0
    assert _duo("Zenyatta", ["Reinhardt", "Cassidy", "Ana"], ["Mauga"], "SUP") == 0  # 1 DPS
    # Jogando de SUP, a regra da dupla não vale para outros suportes.
    assert _duo("Ana", allies, ["Mauga"], role="SUP") == 0


# ---------------------------------------------------------------------------
# Score: coluna DUO = β_duo · termos; TOTAL = META + COUNTER + SYNERGY + DUO
# ---------------------------------------------------------------------------
def _score(hero, allies, enemies, role="DPS", weights=scoring.DEFAULT_WEIGHTS):
    return scoring.calculate_hero_score(
        hero, {}, {}, allies, enemies, {}, {}, weights=weights, role=role, duo_rules=RULES
    )


def test_total_soma_as_quatro_colunas_e_razoes_na_ordem():
    data = scoring.calculate_hero_score(
        "Ashe",
        {"ashe": {"zenyatta": 1.0}},
        {"ashe": {"mauga": 2.0}},
        ["Cassidy", "Zenyatta"],
        ["Mauga"],
        {},
        {"ashe": 1.0},
        mapa="Ilios",
        role="DPS",
        duo_rules=RULES,
    )
    assert data["duo_score"] == pytest.approx(4.0)
    colunas = ("meta_score", "counter_score", "synergy_score", "duo_score")
    soma = sum(float(data[k]) for k in colunas)  # pyright: ignore[reportArgumentType]
    assert data["total"] == pytest.approx(soma)
    # counters, sinergias, dupla, mapa — e os números batem com as colunas.
    assert data["reasons"] == [
        "countera Mauga (+2.00, ameaça 1.00)",
        "sinergia com Zenyatta (+0.65)",
        "dupla Forte+Forte com Cassidy contra Mauga (+2.00)",
        "trio com Zenyatta contra Mauga (+2.00)",
        "forte em Ilios (+1.50)",
    ]


def test_razoes_da_dupla_negativa_e_do_trio_da_zen():
    sigma = _score("Ashe", ["Soldier: 76"], ["Sigma"])
    assert sigma["reasons"] == ["dupla Hitscan+Hitscan com Soldier: 76 contra Sigma (-2.00)"]
    mista = _score("Genji", ["Ashe"], ["D.Va"])
    assert mista["reasons"] == ["dupla Flex+Hitscan com Ashe contra D.Va (+2.00)"]
    zen = _score("Zenyatta", ["Reinhardt", "Cassidy", "Ashe", "Ana"], ["Mauga"], role="SUP")
    assert zen["reasons"] == ["trio com Cassidy e Ashe contra Mauga (+2.00)"]


def test_beta_duo_pondera_a_coluna():
    meio = scoring.resolve_weights("equilibrado", {"beta_duo": 0.5})
    data = _score("Ashe", ["Cassidy", "Zenyatta"], ["Mauga"], weights=meio)
    assert data["duo_score"] == pytest.approx(0.5 * 4)
    reasons = data["reasons"]
    assert isinstance(reasons, list)
    assert "dupla Forte+Forte com Cassidy contra Mauga (+1.00)" in reasons
    zero = scoring.resolve_weights("equilibrado", {"beta_duo": 0.0})
    assert _score("Ashe", ["Cassidy"], ["Mauga"], weights=zero)["duo_score"] == 0.0


def test_sem_duo_rules_a_coluna_fica_em_zero():
    data = scoring.calculate_hero_score("Ashe", {}, {}, ["Cassidy"], ["Mauga"], {}, {})
    assert data["duo_score"] == 0.0


@pytest.mark.parametrize("preset", PRESETS)
def test_beta_duo_e_1_nos_quatro_presets(preset):
    assert scoring.resolve_weights(preset).beta_duo == scoring.BETA_DUO == 1.0


def test_beta_syn_dps_dps_saiu_e_beta_duo_entrou_no_custom_weights():
    assert "beta_duo" in scoring.WEIGHT_FIELD_NAMES
    assert "beta_syn_dps_dps" not in scoring.WEIGHT_FIELD_NAMES
    cfg, problems = settings.parse({"custom_weights": {"beta_duo": 0.5}})
    assert problems == [] and cfg.custom_weights == {"beta_duo": 0.5}
    cfg, problems = settings.parse({"custom_weights": {"beta_syn_dps_dps": 0.65}})
    assert cfg.custom_weights == {} and len(problems) == 1


def test_rank_heroes_preenche_a_coluna_duo():
    recs, _ = scoring.rank_heroes(
        ["Ashe", "Genji", "Tracer"],
        ["Tracer"],
        ["Mauga"],
        {},
        {},
        {},
        {},
        excluded_keys={"tracer"},
        role="DPS",
        duo_rules=RULES,
    )
    assert [(r.hero.name, r.duo, r.total) for r in recs] == [
        ("Ashe", 0.0, 0.0),
        ("Genji", -2.0, -2.0),
    ]


# ---------------------------------------------------------------------------
# Enemy Threat: 4º termo −λ·D(tank), só com a dupla aliada já formada
# ---------------------------------------------------------------------------
ENEMIES_MAUGA = ["Mauga", "Tracer", "Genji", "Kiriko", "Lúcio"]


def _w(enemies, allies, role, preset="equilibrado", rules: DuoRules | None = RULES):
    p = scoring.resolve_weights(preset)
    return scoring.compute_threat_weights(
        enemies, {}, allies, {}, lam=p.lam, mu=p.mu, nu=p.nu, role=role, duo_rules=rules
    )


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("role", ["SUP", "TANK"])
def test_dupla_aliada_que_o_tank_sofre_reduz_a_ameaca(role, preset):
    allies = (
        ["Reinhardt", "Cassidy", "Ashe", "Ana"]
        if role == "SUP"
        else ["Cassidy", "Ashe", "Ana", "Mercy"]
    )
    lam = scoring.resolve_weights(preset).lam
    w = _w(ENEMIES_MAUGA, allies, role, preset)
    assert w["mauga"] == pytest.approx(scoring.threat_multiplier(-2 * lam))
    assert all(w[k] == pytest.approx(1.0) for k in ("tracer", "genji", "kiriko", "lucio"))


def test_trio_da_zen_tira_mais_2_lambda():
    lam = scoring.LAMBDA
    w = _w(ENEMIES_MAUGA, ["Reinhardt", "Cassidy", "Ashe", "Zenyatta"], "SUP")
    assert w["mauga"] == pytest.approx(scoring.threat_multiplier(-4 * lam))
    w = _w(["D.Mon", "Tracer"], ["Cassidy", "Ashe", "Zenyatta", "Ana"], "TANK")
    assert w["dmon"] == pytest.approx(scoring.threat_multiplier(-4 * lam))


def test_dupla_que_favorece_o_tank_aumenta_a_ameaca():
    lam = scoring.LAMBDA
    up = scoring.threat_multiplier(2 * lam)
    assert _w(ENEMIES_MAUGA, ["Reinhardt", "Genji", "Tracer", "Ana"], "SUP")[
        "mauga"
    ] == pytest.approx(up)
    assert _w(["Sigma", "Ana"], ["Reinhardt", "Ashe", "Soldier: 76", "Ana"], "SUP")[
        "sigma"
    ] == pytest.approx(up)
    assert _w(["D.Va", "Ana"], ["Reinhardt", "Ashe", "Genji", "Ana"], "SUP")[
        "dva"
    ] == pytest.approx(scoring.threat_multiplier(-2 * lam))


@pytest.mark.parametrize(
    ("allies", "enemies", "role"),
    [
        (["Reinhardt", "Cassidy", "Ana", "Kiriko"], ENEMIES_MAUGA, "DPS"),  # jogando de DPS
        (["Reinhardt", "Cassidy", "Ashe", "Ana"], ENEMIES_MAUGA, "DPS"),  # DPS + 2 DPS (sim)
        (["Reinhardt", "Cassidy", "Ashe", "Ana"], ENEMIES_MAUGA, "ALL"),  # Fila Aberta
        (["Reinhardt", "Cassidy", "Ana", "Kiriko"], ENEMIES_MAUGA, "SUP"),  # 1 DPS aliado
        (["Cassidy", "Ashe", "Sojourn", "Ana"], ENEMIES_MAUGA, "TANK"),  # 3 DPS aliados
        (["Reinhardt", "Cassidy", "Ashe", "Ana"], ["Mauga", "Sigma", "Ana"], "SUP"),  # 2 tanks
    ],
)
def test_ameaca_fora_das_condicoes_fica_como_antes(allies, enemies, role):
    w = _w(enemies, allies, role)
    assert all(v == pytest.approx(1.0) for v in w.values()), w
    for enemy in enemies:
        assert duo_threat_value(enemy, allies, enemies, role, RULES) == 0.0


def test_sem_duo_rules_a_ameaca_nao_muda():
    w = _w(ENEMIES_MAUGA, ["Reinhardt", "Cassidy", "Ashe", "Ana"], "SUP", rules=None)
    assert w["mauga"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Pipeline: role do jogador chega ao ranking e à ameaça
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    settings.reload()
    yield tmp_path
    settings.reload()


def test_pipeline_rank_aplica_a_regra_pela_role(isolated_settings):
    from owpick import pipeline

    dps = pipeline.rank("DPS", ["Ashe", "Genji"], ["Cassidy"], ["Mauga"], [], "UNKNOWN")
    assert {r.hero.name: r.duo for r in dps.recommendations} == {"Ashe": 2.0, "Genji": 0.0}

    allies = ["Reinhardt", "Cassidy", "Ashe", "Ana"]
    sup = pipeline.rank("SUP", ["Zenyatta", "Kiriko"], allies, ["Mauga"], [], "UNKNOWN")
    assert {r.hero.name: r.duo for r in sup.recommendations} == {"Zenyatta": 2.0, "Kiriko": 0.0}
    sem_dupla = scoring.compute_threat_weights(
        ["Mauga"],
        datasource.get_enemy_matrix(),
        allies,
        {},
        synergy_matrix=datasource.get_ally_matrix(),
    )
    assert sup.threat_weights["mauga"] < sem_dupla["mauga"]


# ---------------------------------------------------------------------------
# Matrizes: bloco DPS x DPS vazio e os 7 pares tank x DPS gravados em counters
# ---------------------------------------------------------------------------
def test_bloco_dps_x_dps_da_matriz_de_sinergias_esta_vazio():
    ally = datasource.get_ally_matrix()
    dps = [normalize_hero_name(h) for h in heroes.HEROES_ROLES["DPS"]]
    preenchidas = [(a, b) for a in dps for b in dps if a != b and b in ally[a]]
    assert preenchidas == []
    assert all(a in ally[a] for a in dps)  # diagonal intocada


@pytest.mark.parametrize(
    ("tank", "dps", "valor"),
    [
        ("D.Va", "Bastion", 1),
        ("D.Va", "Hanzo", 1),
        ("D.Va", "Junkrat", 1),
        ("D.Va", "Sierra", 1),
        ("D.Va", "Soldier: 76", 1),
        ("Zarya", "Mei", -1),
        ("Sigma", "Hanzo", 1),
    ],
)
def test_valores_individuais_gravados_nos_counters(tank, dps, valor):
    """Convenção da matriz: C(Tank, DPS) > 0 = o tank leva vantagem (o DPS perde
    prioridade com esse tank inimigo); o espelho é C(DPS, Tank) = −valor."""
    enemy = datasource.get_enemy_matrix()
    t, d = normalize_hero_name(tank), normalize_hero_name(dps)
    assert enemy[t][d] == valor
    assert enemy[d][t] == -valor
