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
        {"sniper": 2.0, "anchor": 4.0, "buddy": 1.3}
    )  # snapshot do modelo atual (β_meta=2.0)


def test_snapshot_counter_first():
    # β_meta=1.0, β_ctr=1.50, β_syn=0.50 -> counter domina.
    totals = _totals(resolve_weights("counter-first"))
    assert totals == pytest.approx({"sniper": 3.0, "anchor": 2.0, "buddy": 1.0})
    assert max(totals, key=lambda h: totals[h]) == "sniper"


def test_snapshot_meta_first():
    # β_meta=4.0 -> o herói forte no mapa dispara.
    totals = _totals(resolve_weights("meta-first"))
    assert totals == pytest.approx({"sniper": 2.0, "anchor": 8.0, "buddy": 1.3})
    assert max(totals, key=lambda h: totals[h]) == "anchor"


def test_snapshot_conforto_mais():
    # "equilibrado" com β_syn=1.25: a sinergia do "buddy" sobe (1.3 -> 2.5).
    totals = _totals(resolve_weights("conforto+"))
    assert totals == pytest.approx({"sniper": 2.0, "anchor": 4.0, "buddy": 2.5})
    assert totals["buddy"] > _totals(resolve_weights("equilibrado"))["buddy"]


def test_custom_weights_sobrescreve_preset():
    w = resolve_weights("equilibrado", {"beta_syn": 2.0, "campo_invalido": 9.9})
    assert w.beta_syn == 2.0
    assert w.beta_meta == 2.0  # demais campos do preset preservados


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
