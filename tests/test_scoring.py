"""Testes do modelo de scoring (owpick.core.scoring) com dados sintéticos."""

import math

import pandas as pd
import pytest

from owpick.core import scoring


def softplus(x: float) -> float:
    return math.log1p(math.exp(x))


# ---------------------------------------------------------------------------
# load_meta_strength — DataFrame sintético com valores calculados à mão
# ---------------------------------------------------------------------------


class TestLoadMetaStrength:
    @pytest.fixture()
    def stats_df(self):
        # 3 DPS no mesmo mapa, pickrate exatamente na taxa neutra da role
        # (2/24 -> conf = 0.5). winrates 50/55/45: média 50, std (ddof=1) = 5.
        neutral_pct = 100.0 * 2 / 24
        return pd.DataFrame(
            {
                "map": ["TestMap"] * 3,
                "hero": ["A", "B", "C"],
                "role": ["DPS"] * 3,
                "winrate": [50.0, 55.0, 45.0],
                "pickrate": [neutral_pct] * 3,
            }
        )

    def test_z_score_por_role_com_confianca(self, stats_df):
        meta = scoring.load_meta_strength(stats_df, "TestMap")
        # m = alpha * clip(conf * z) = 2.25 * 0.5 * z, com z em {0, +1, -1}
        assert meta["a"] == pytest.approx(0.0)
        assert meta["b"] == pytest.approx(scoring.ALPHA * 0.5 * 1.0)
        assert meta["c"] == pytest.approx(-scoring.ALPHA * 0.5 * 1.0)

    def test_clamp_em_mmax(self, stats_df):
        meta = scoring.load_meta_strength(stats_df, "TestMap", mmax=0.3)
        assert meta["b"] == pytest.approx(scoring.ALPHA * 0.3)

    def test_mapa_unknown_retorna_vazio(self, stats_df):
        assert scoring.load_meta_strength(stats_df, "UNKNOWN") == {}
        assert scoring.load_meta_strength(stats_df, "") == {}

    def test_mapa_sem_dados_retorna_vazio(self, stats_df):
        assert scoring.load_meta_strength(stats_df, "Outro Mapa") == {}

    def test_fallback_nome_de_mapa_normalizado(self, stats_df):
        stats_df["map"] = ["Paraíso"] * 3
        meta = scoring.load_meta_strength(stats_df, "paraiso")
        assert meta  # encontrado via comparação normalizada


# ---------------------------------------------------------------------------
# compute_threat_weights — softplus(1 + λ·ΣC(e,a) + μ·m(e,k))
# ---------------------------------------------------------------------------


class TestComputeThreatWeights:
    def test_valores_calculados_a_mao(self):
        enemy_matrix = {"e1": {"a1": 2.0}, "e2": {}}
        meta = {"e1": 1.0}
        weights = scoring.compute_threat_weights(
            ["E1", "E2"], enemy_matrix, ["A1"], meta_strength=meta
        )
        raw_e1 = 1.0 + scoring.LAMBDA * 2.0 + scoring.MU_THREAT * 1.0
        assert weights["e1"] == pytest.approx(softplus(raw_e1))
        assert weights["e2"] == pytest.approx(softplus(1.0))  # neutro

    def test_softplus_sempre_positivo_e_monotonico(self):
        enemy_matrix = {"fraco": {"a": -50.0}, "forte": {"a": 50.0}}
        w = scoring.compute_threat_weights(["fraco", "forte"], enemy_matrix, ["a"])
        assert 0.0 < w["fraco"] < w["forte"]

    def test_nomes_normalizados(self):
        enemy_matrix = {"dva": {"soldier-76": 3.0}}
        w = scoring.compute_threat_weights(["D.Va"], enemy_matrix, ["Soldier: 76"])
        assert w["dva"] == pytest.approx(softplus(1.0 + scoring.LAMBDA * 3.0))


# ---------------------------------------------------------------------------
# calculate_hero_score — lineup sintético, matriz de 3 heróis, valores à mão
# ---------------------------------------------------------------------------


class TestCalculateHeroScore:
    def test_decomposicao_completa(self):
        ally_matrix = {"h": {"a1": 1.0, "h": 5.0}}
        enemy_matrix = {"h": {"e1": 2.0, "e2": -1.0}}
        threat = {"e1": 1.5, "e2": 1.0}
        meta = {"h": 0.5}

        r = scoring.calculate_hero_score(
            "H",
            ally_matrix,
            enemy_matrix,
            allies=["A1", "H"],
            enemies=["E1", "E2"],
            threat_weights=threat,
            meta_strength=meta,
        )
        assert r["counter_score"] == pytest.approx(1.5 * 2.0 + 1.0 * (-1.0))  # 2.0
        # diagonal (h com h) ignorada; só a1 conta
        assert r["synergy_score"] == pytest.approx(1.0 * scoring.BETA_SYN)  # 0.65
        assert r["meta_score"] == pytest.approx(0.5)
        assert r["total"] == pytest.approx(
            scoring.BETA_META * 0.5 + scoring.BETA_CTR * 2.0 + 1.0 * scoring.BETA_SYN
        )

    def test_hero_sem_dados_score_zero(self):
        r = scoring.calculate_hero_score("Desconhecido", {}, {}, ["a"], ["e"], {}, {})
        assert r["total"] == 0.0

    def test_inimigo_sem_threat_weight_usa_1(self):
        enemy_matrix = {"h": {"e1": 2.0}}
        r = scoring.calculate_hero_score("H", {}, enemy_matrix, [], ["E1"], {}, {})
        assert r["counter_score"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# rank_heroes — caso de uso puro -> list[Recommendation]
# ---------------------------------------------------------------------------


class TestRankHeroes:
    def test_ordena_e_exclui(self):
        ally_matrix: dict = {}
        enemy_matrix = {"tracer": {"e1": 3.0}, "genji": {"e1": 1.0}}
        threat = {"e1": 1.0}
        recs, excluded = scoring.rank_heroes(
            ["Tracer", "Genji", "Ashe"],
            allies=[],
            enemies=["E1"],
            ally_matrix=ally_matrix,
            enemy_matrix=enemy_matrix,
            threat_weights=threat,
            meta_strength={},
            excluded_keys={"ashe"},
        )
        assert [r.hero.name for r in recs] == ["Tracer", "Genji"]  # ordenado desc
        assert excluded == ["Ashe"]
        assert recs[0].total > recs[1].total
