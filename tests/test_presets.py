"""Testes dos presets de pesos do modelo (tarefa 6.3).

Snapshot tests: um cenário sintético fixo mostra o EFEITO de cada preset —
qual termo passa a dominar o ranking quando o preset muda.
"""

import pytest

from owpick import settings
from owpick.core import scoring
from owpick.core.scoring import ModelWeights, calculate_hero_score, resolve_weights

# Cenário sintético: "sniper" countera bem; "anchor" tem meta forte no mapa;
# "buddy" sinergiza com o time. Matrizes mínimas (chaves já normalizadas).
ENEMIES = ["alvo"]
ALLIES = ["parceiro"]
ENEMY_MATRIX = {
    "sniper": {"alvo": 2.0},
    "anchor": {"alvo": 0.0},
    "buddy": {"alvo": 0.0},
}
ALLY_MATRIX = {
    "sniper": {"parceiro": 0.0},
    "anchor": {"parceiro": 0.0},
    "buddy": {"parceiro": 2.0},
}
META = {"sniper": 0.0, "anchor": 2.0, "buddy": 0.0}
THREAT = {"alvo": 1.0}


def _totals(weights: ModelWeights) -> dict[str, float]:
    return {
        hero: float(
            calculate_hero_score(
                hero, ALLY_MATRIX, ENEMY_MATRIX, ALLIES, ENEMIES, THREAT, META, weights=weights
            )["total"]  # pyright: ignore[reportArgumentType]
        )
        for hero in ("sniper", "anchor", "buddy")
    }


def test_preset_equilibrado_e_o_modelo_atual():
    """ "equilibrado" == defaults == constantes do módulo (compatibilidade)."""
    w = resolve_weights("equilibrado")
    assert w == ModelWeights()
    assert (w.alpha, w.lam, w.mu) == (scoring.ALPHA, scoring.LAMBDA, scoring.MU_THREAT)
    assert (w.beta_meta, w.beta_ctr, w.beta_syn) == (
        scoring.BETA_META,
        scoring.BETA_CTR,
        scoring.BETA_SYN,
    )
    # Sem weights explícito, calculate_hero_score usa os mesmos defaults.
    baseline = _totals(ModelWeights())
    assert baseline == pytest.approx(
        {"sniper": 2.0, "anchor": 3.0, "buddy": 1.3}
    )  # snapshot do modelo atual (β_meta=1.5)


def test_snapshot_counter_first():
    # β_meta=0.75, β_ctr=1.00, β_syn=0.325 -> counter domina.
    totals = _totals(resolve_weights("counter-first"))
    assert totals == pytest.approx({"sniper": 2.0, "anchor": 1.5, "buddy": 0.65})
    assert max(totals, key=lambda h: totals[h]) == "sniper"


def test_counter_first_sinergia_sup_x_sup_usa_peso_dobrado():
    """No counter-first, SUP × SUP usa β_syn_sup_sup=0.65; o resto, β_syn=0.325."""
    w = resolve_weights("counter-first")
    ally_matrix = {"ana": {"mercy": 1.0, "cassidy": 1.0}}

    def _syn(ally: str) -> float:
        return float(
            calculate_hero_score("Ana", ally_matrix, {}, [ally], [], {}, {}, weights=w)[
                "synergy_score"
            ]  # pyright: ignore[reportArgumentType]
        )

    assert _syn("Mercy") == pytest.approx(0.65)  # SUP × SUP
    assert _syn("Cassidy") == pytest.approx(0.325)  # SUP × DPS
    # Os demais presets não têm a regra: tudo usa β_syn.
    eq = resolve_weights("equilibrado")
    assert float(
        calculate_hero_score("Ana", ally_matrix, {}, ["Mercy"], [], {}, {}, weights=eq)[
            "synergy_score"
        ]  # pyright: ignore[reportArgumentType]
    ) == pytest.approx(scoring.BETA_SYN)


def test_sinergia_dps_x_dps_usa_peso_fixo_de_065():
    """Pares DPS × DPS usam β_syn_dps_dps=0.65 em TODOS os presets, menos o
    "conforto+" (que mantém o β_syn próprio, 1.25)."""
    ally_matrix = {"cassidy": {"ana": 1.0, "ashe": -6.0}}

    def _syn(preset: str, ally: str) -> float:
        return float(
            calculate_hero_score(
                "Cassidy", ally_matrix, {}, [ally], [], {}, {}, weights=resolve_weights(preset)
            )["synergy_score"]  # pyright: ignore[reportArgumentType]
        )

    # Y(Cassidy, Ashe) = -6 (DPS × DPS): peso fixo 0.65 -> -3.9 nos 3 presets.
    for preset in ("equilibrado", "counter-first", "meta-first"):
        assert _syn(preset, "Ashe") == pytest.approx(-6 * 0.65), preset
    # Y(Cassidy, Ana) = 1 (DPS × SUP): usa o β_syn NORMAL de cada preset.
    assert _syn("counter-first", "Ana") == pytest.approx(0.325)
    assert _syn("equilibrado", "Ana") == pytest.approx(0.65)
    # "conforto+" não tem a regra: DPS × DPS usa o β_syn cheio (1.25).
    assert _syn("conforto+", "Ashe") == pytest.approx(-6 * 1.25)
    assert _syn("conforto+", "Ana") == pytest.approx(1.25)


def test_precedencia_sup_sup_sobre_dps_dps_e_beta_syn():
    """Precedência: SUP × SUP -> β_syn_sup_sup; DPS × DPS -> β_syn_dps_dps; senão β_syn."""
    w = resolve_weights("counter-first")
    assert w.beta_syn_sup_sup == 0.325 * 2  # 0.65
    assert w.beta_syn_dps_dps == 0.65
    # Um par SUP × SUP nunca cai na regra de DPS (roles distintas não se cruzam).
    ally_matrix = {"ana": {"mercy": 1.0}, "cassidy": {"ashe": 1.0}}
    sup = float(
        calculate_hero_score("Ana", ally_matrix, {}, ["Mercy"], [], {}, {}, weights=w)[
            "synergy_score"
        ]  # pyright: ignore[reportArgumentType]
    )
    dps = float(
        calculate_hero_score("Cassidy", ally_matrix, {}, ["Ashe"], [], {}, {}, weights=w)[
            "synergy_score"
        ]  # pyright: ignore[reportArgumentType]
    )
    assert sup == pytest.approx(0.65)
    assert dps == pytest.approx(0.65)
    # Par de roles diferentes: β_syn normal do preset.
    misto = float(
        calculate_hero_score(
            "Cassidy", {"cassidy": {"ana": 1.0}}, {}, ["Ana"], [], {}, {}, weights=w
        )["synergy_score"]  # pyright: ignore[reportArgumentType]
    )
    assert misto == pytest.approx(0.325)


def test_sinergia_mercy_x_dps_usa_peso_fixo_de_1():
    """O par Mercy × DPS usa β_syn_mercy_dps=1 nos QUATRO presets."""
    ally_matrix = {"mercy": {"cassidy": 1.0, "winston": 1.0, "ana": 2.0}}

    def _syn(preset: str, ally: str) -> float:
        return float(
            calculate_hero_score(
                "Mercy", ally_matrix, {}, [ally], [], {}, {}, weights=resolve_weights(preset)
            )["synergy_score"]  # pyright: ignore[reportArgumentType]
        )

    for preset in ("equilibrado", "counter-first", "meta-first", "conforto+"):
        w = resolve_weights(preset)
        assert w.beta_syn_mercy_dps == scoring.BETA_SYN_MERCY_DPS  # nenhum preset desliga
        assert _syn(preset, "Cassidy") == pytest.approx(1.0), preset  # Y=1 -> 1 × 1
        # Mercy × TANK e Mercy × SUP seguem os pesos normais do preset.
        assert _syn(preset, "Winston") == pytest.approx(w.beta_syn), preset
        beta_sup = w.beta_syn_sup_sup if w.beta_syn_sup_sup is not None else w.beta_syn
        assert _syn(preset, "Ana") == pytest.approx(2.0 * beta_sup), preset


def test_precedencia_mercy_dps_nunca_colide_com_as_excecoes_de_mesma_role():
    """SUP × SUP → DPS × DPS → Mercy × DPS → β_syn (as duas primeiras exigem a
    MESMA role; a terceira, roles distintas — nunca competem pelo mesmo par)."""
    w = resolve_weights("counter-first")
    assert scoring._pair_beta_syn(w, "SUP", "SUP", "mercy", "ana") == pytest.approx(0.65)
    assert scoring._pair_beta_syn(w, "DPS", "DPS", "cassidy", "ashe") == pytest.approx(0.65)
    assert scoring._pair_beta_syn(w, "SUP", "DPS", "mercy", "cassidy") == pytest.approx(1.0)
    assert scoring._pair_beta_syn(w, "DPS", "SUP", "cassidy", "mercy") == pytest.approx(1.0)
    # Mercy × TANK e outro SUP × DPS caem no β_syn genérico.
    assert scoring._pair_beta_syn(w, "SUP", "TANK", "mercy", "winston") == pytest.approx(0.325)
    assert scoring._pair_beta_syn(w, "SUP", "DPS", "ana", "cassidy") == pytest.approx(0.325)


def test_snapshot_meta_first():
    # β_meta=3.0 -> o herói forte no mapa dispara.
    totals = _totals(resolve_weights("meta-first"))
    assert totals == pytest.approx({"sniper": 2.0, "anchor": 6.0, "buddy": 1.3})
    assert max(totals, key=lambda h: totals[h]) == "anchor"


def test_snapshot_conforto_mais():
    # "equilibrado" com β_syn=1.25: a sinergia do "buddy" sobe (1.3 -> 2.5).
    totals = _totals(resolve_weights("conforto+"))
    assert totals == pytest.approx({"sniper": 2.0, "anchor": 3.0, "buddy": 2.5})
    assert totals["buddy"] > _totals(resolve_weights("equilibrado"))["buddy"]


def test_custom_weights_sobrescreve_preset():
    w = resolve_weights("equilibrado", {"beta_syn": 2.0, "campo_invalido": 9.9})
    assert w.beta_syn == 2.0
    assert w.beta_meta == 1.5  # demais campos do preset preservados


def test_preset_desconhecido_cai_para_equilibrado():
    assert resolve_weights("turbo") == ModelWeights()


# ---------------------------------------------------------------------------
# Validação no settings
# ---------------------------------------------------------------------------
def test_settings_valida_preset_e_custom_weights():
    cfg, problems = settings.parse(
        {"weights_preset": "counter-first", "custom_weights": {"beta_ctr": 1.2}}
    )
    assert problems == []
    assert cfg.weights_preset == "counter-first"
    assert cfg.custom_weights == {"beta_ctr": 1.2}

    cfg, problems = settings.parse({"weights_preset": "turbo", "custom_weights": {"nao_existe": 1}})
    assert cfg.weights_preset == "equilibrado"
    assert cfg.custom_weights == {}
    assert len(problems) == 2
