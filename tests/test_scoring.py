"""Testes do modelo de scoring (owpick.core.scoring) com dados sintéticos."""

import math

import pandas as pd
import pytest

from owpick.core import scoring

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
# threat_multiplier / compute_threat_weights — w = CAP ** tanh(raw / SCALE)
# ---------------------------------------------------------------------------


class TestThreatMultiplier:
    def test_ancoras(self):
        # A curva passa EXATAMENTE pelos dois pontos escolhidos + pelo neutro.
        assert scoring.threat_multiplier(0.0) == pytest.approx(1.0)
        assert scoring.threat_multiplier(-1.5) == pytest.approx(0.6)
        assert scoring.threat_multiplier(3.0) == pytest.approx(2.5)

    def test_neutro_negativo_positivo(self):
        # raw = 0 -> 1 exato; raw < 0 -> < 1; raw > 0 -> > 1.
        assert scoring.threat_multiplier(-1.0) < 1.0 < scoring.threat_multiplier(1.0)

    def test_limites_e_log_simetria(self):
        cap = math.exp(scoring.THREAT_LOG_CAP)  # teto assintótico (e^A)
        # No limite tanh -> ±1 o multiplicador satura nas assíntotas 1/cap e cap
        # (nunca as ultrapassa) — em raw finito fica no interior.
        assert scoring.threat_multiplier(-1e4) == pytest.approx(1.0 / cap)
        assert scoring.threat_multiplier(1e4) == pytest.approx(cap)
        assert scoring.threat_multiplier(-1e4) < 1.0 < scoring.threat_multiplier(1e4)
        # Log-simetria: w(-raw) = 1 / w(raw).
        assert scoring.threat_multiplier(-2.3) == pytest.approx(
            1.0 / scoring.threat_multiplier(2.3)
        )

    def test_monotonica(self):
        vals = [scoring.threat_multiplier(r) for r in (-8, -6, -2, -0.5, 0, 0.5, 2, 6, 8, 10)]
        assert vals == sorted(vals)
        assert all(a < b for a, b in zip(vals, vals[1:], strict=False))


class TestComputeThreatWeights:
    def test_valores_calculados_a_mao(self):
        enemy_matrix = {"e1": {"a1": 2.0}, "e2": {}}
        meta = {"e1": 1.0}
        weights = scoring.compute_threat_weights(
            ["E1", "E2"], enemy_matrix, ["A1"], meta_strength=meta
        )
        raw_e1 = scoring.LAMBDA * 2.0 + scoring.MU_THREAT * 1.0  # sem offset +1
        assert weights["e1"] == pytest.approx(scoring.threat_multiplier(raw_e1))
        assert weights["e2"] == pytest.approx(1.0)  # raw = 0 -> neutro

    def test_positivo_e_monotonico(self):
        enemy_matrix = {"fraco": {"a": -50.0}, "forte": {"a": 50.0}}
        w = scoring.compute_threat_weights(["fraco", "forte"], enemy_matrix, ["a"])
        # Limitado a (e^-A, e^A) por construção e ordenado.
        cap = math.exp(scoring.THREAT_LOG_CAP)
        assert 1.0 / cap < w["fraco"] < 1.0 < w["forte"] < cap

    def test_nomes_normalizados(self):
        enemy_matrix = {"dva": {"soldier-76": 3.0}}
        w = scoring.compute_threat_weights(["D.Va"], enemy_matrix, ["Soldier: 76"])
        assert w["dva"] == pytest.approx(scoring.threat_multiplier(scoring.LAMBDA * 3.0))

    def test_sinergia_do_time_inimigo(self):
        # Inimigo que sinergiza com o RESTO do time inimigo fica mais ameaçador;
        # a diagonal (e' == e) é ignorada.
        enemy_matrix: dict = {}
        synergy_matrix = {"e1": {"e2": 2.0, "e3": 1.0, "e1": 9.0}}
        w = scoring.compute_threat_weights(
            ["E1", "E2", "E3"],
            enemy_matrix,
            allies=[],
            synergy_matrix=synergy_matrix,
        )
        # raw_e1 = ν · (2.0 + 1.0), diagonal e1↔e1 (9.0) ignorada.
        assert w["e1"] == pytest.approx(scoring.threat_multiplier(scoring.NU_THREAT * 3.0))
        assert w["e2"] == pytest.approx(1.0)  # sem linha de sinergia -> neutro

    def test_sinergia_ausente_e_compativel(self):
        # Sem synergy_matrix o termo ν some (compatibilidade retroativa).
        enemy_matrix = {"e1": {"a1": 2.0}}
        w = scoring.compute_threat_weights(["E1", "E2"], enemy_matrix, ["A1"])
        assert w["e1"] == pytest.approx(scoring.threat_multiplier(scoring.LAMBDA * 2.0))


# ---------------------------------------------------------------------------
# Exclusão de pares de MESMA role no termo de sinergia da ameaça (v1.2.12)
# ---------------------------------------------------------------------------


class TestThreatSynergyPairExclusion:
    """SUP × SUP e DPS × DPS contribuem 0 no somatório ν do threat weighting.

    Vale em TODOS os presets (inclusive conforto+) — ao contrário da regra de
    β_syn_dps_dps do ranking, que não se aplica ao conforto+.
    """

    @pytest.mark.parametrize("preset", ["equilibrado", "counter-first", "meta-first", "conforto+"])
    def test_dps_x_dps_nao_soma_ameaca(self, preset):
        # Cassidy × Ashe: dois DPS (Hitscan), Y = -6 -> contribuição 0 (w_e = 1).
        w_preset = scoring.resolve_weights(preset)
        synergy_matrix = {"cassidy": {"ashe": -6.0}, "ashe": {"cassidy": -6.0}}
        w = scoring.compute_threat_weights(
            ["Cassidy", "Ashe"],
            {},
            allies=[],
            lam=w_preset.lam,
            mu=w_preset.mu,
            synergy_matrix=synergy_matrix,
            nu=w_preset.nu,
        )
        assert w["cassidy"] == pytest.approx(1.0)
        assert w["ashe"] == pytest.approx(1.0)

    def test_dps_x_dps_de_categorias_diferentes_tambem_e_zero(self):
        # Ashe × Genji: sinergia POSITIVA que conta no T_syn, mas 0 na ameaça.
        synergy_matrix = {"ashe": {"genji": 2.0}, "genji": {"ashe": 2.0}}
        w = scoring.compute_threat_weights(
            ["Ashe", "Genji"], {}, allies=[], synergy_matrix=synergy_matrix
        )
        assert w["ashe"] == pytest.approx(1.0)
        assert w["genji"] == pytest.approx(1.0)

    def test_sup_x_sup_continua_excluido(self):
        synergy_matrix = {"ana": {"mercy": 2.0}, "mercy": {"ana": 2.0}}
        w = scoring.compute_threat_weights(
            ["Ana", "Mercy"], {}, allies=[], synergy_matrix=synergy_matrix
        )
        assert w["ana"] == pytest.approx(1.0)
        assert w["mercy"] == pytest.approx(1.0)

    def test_pares_de_roles_diferentes_continuam_contando(self):
        # DPS × TANK e DPS × SUP não são excluídos — a regra é só MESMA role.
        synergy_matrix = {"cassidy": {"winston": 2.0, "ana": 1.0}}
        w = scoring.compute_threat_weights(
            ["Cassidy", "Winston", "Ana"], {}, allies=[], synergy_matrix=synergy_matrix
        )
        assert w["cassidy"] == pytest.approx(scoring.threat_multiplier(scoring.NU_THREAT * 3.0))
        assert w["cassidy"] > 1.0


# ---------------------------------------------------------------------------
# Threat weighting do "pocket" da Mercy (v1.2.12)
# ---------------------------------------------------------------------------


class TestMercyPocket:
    """Mercy + DPS pocketável: ×1.5 no DPS de maior prioridade, ×0.5 na Mercy.

    Os w_e base são todos 1.0 (matrizes vazias ⇒ raw = 0), então o dict de saída
    mostra o MULTIPLICADOR final de cada herói diretamente.
    """

    @staticmethod
    def _w(enemies, preset="equilibrado"):
        p = scoring.resolve_weights(preset)
        return scoring.compute_threat_weights(enemies, {}, allies=[], lam=p.lam, mu=p.mu, nu=p.nu)

    def test_mercy_pharah_ashe_so_a_pharah_sobe(self):
        # Prioridade: Pharah > Ashe -> só a Pharah é pocketada; a Ashe fica ×1.
        w = self._w(["Mercy", "Pharah", "Ashe"])
        assert w["pharah"] == pytest.approx(1.5)
        assert w["mercy"] == pytest.approx(0.5)
        assert w["ashe"] == pytest.approx(1.0)

    def test_bastion_mais_emre_cancela_o_ajuste(self):
        w = self._w(["Bastion", "Emre", "Mercy"])
        assert w["bastion"] == pytest.approx(1.0)
        assert w["emre"] == pytest.approx(1.0)
        assert w["mercy"] == pytest.approx(1.0)

    def test_bastion_mais_pharah_nao_e_gatilho_da_excecao(self):
        # Pharah NÃO está no subconjunto {Sierra, Emre, Cassidy, Soldier: 76}.
        w = self._w(["Bastion", "Pharah", "Mercy"])
        assert w["bastion"] == pytest.approx(1.0)
        assert w["pharah"] == pytest.approx(1.5)
        assert w["mercy"] == pytest.approx(0.5)

    def test_excecao_do_bastion_tem_precedencia_sobre_a_prioridade(self):
        # Bastion + Emre cancela TUDO, mesmo com a Pharah (maior prioridade).
        w = self._w(["Bastion", "Emre", "Pharah", "Mercy"])
        assert all(v == pytest.approx(1.0) for v in w.values()), w

    def test_ordem_de_prioridade_completa(self):
        # O primeiro da lista presente vence, qualquer que seja a ordem do lineup.
        ordem = [
            "Pharah",
            "Sojourn",
            "Ashe",
            "Freja",
            "Echo",
            "Sierra",
            "Emre",
            "Cassidy",
            "Soldier: 76",
        ]
        for i, esperado in enumerate(ordem):
            # Time com Mercy + todos os DPS a partir de `i` (em ordem invertida,
            # para provar que a escolha não depende da posição no lineup).
            enemies = ["Mercy", *reversed(ordem[i:])]
            w = self._w(enemies)
            alvo = scoring.normalize_hero_name(esperado)
            assert w[alvo] == pytest.approx(1.5), f"{esperado} deveria ser o pocket"
            assert w["mercy"] == pytest.approx(0.5)
            outros = [scoring.normalize_hero_name(h) for h in ordem[i:] if h != esperado]
            assert all(w[o] == pytest.approx(1.0) for o in outros)

    def test_sem_mercy_nao_ha_ajuste(self):
        w = self._w(["Pharah", "Ashe"])
        assert w["pharah"] == pytest.approx(1.0)
        assert w["ashe"] == pytest.approx(1.0)

    def test_mercy_sem_dps_da_lista_nao_ha_ajuste(self):
        w = self._w(["Mercy", "Genji", "Winston"])
        assert all(v == pytest.approx(1.0) for v in w.values()), w

    @pytest.mark.parametrize("preset", ["equilibrado", "counter-first", "meta-first", "conforto+"])
    def test_vale_em_todos_os_presets(self, preset):
        w = self._w(["Mercy", "Sojourn"], preset)
        assert w["sojourn"] == pytest.approx(1.5)
        assert w["mercy"] == pytest.approx(0.5)

    def test_multiplica_o_w_e_ja_calculado(self):
        # O ajuste é sobre o w_e PRONTO (não entra no raw nem passa pela curva).
        enemy_matrix = {"pharah": {"a1": 2.0}}
        w = scoring.compute_threat_weights(["Mercy", "Pharah"], enemy_matrix, ["A1"])
        base = scoring.threat_multiplier(scoring.LAMBDA * 2.0)
        assert w["pharah"] == pytest.approx(base * 1.5)
        assert w["mercy"] == pytest.approx(0.5)

    def test_nao_muta_o_dict_de_entrada(self):
        base = {"mercy": 1.0, "pharah": 2.0}
        out = scoring.apply_mercy_pocket(base, ["mercy", "pharah"])
        assert base == {"mercy": 1.0, "pharah": 2.0}  # intacto
        assert out == pytest.approx({"mercy": 0.5, "pharah": 3.0})


# ---------------------------------------------------------------------------
# Sinergia Mercy × DPS no T_syn ALIADO (v1.2.13) — peso 1 + "DPS prioritário"
# ---------------------------------------------------------------------------

TODOS_OS_PRESETS = ["equilibrado", "counter-first", "meta-first", "conforto+"]

# Linha da Mercy com os valores reais de Y(Mercy, <DPS>) (tarefa 1), mais um
# Tank e uma SUP para provar que a regra do "DPS prioritário" não os toca.
_MERCY_Y: dict[str, float] = {
    **dict.fromkeys(("Pharah", "Sojourn", "Ashe", "Freja", "Echo"), 2.0),
    **dict.fromkeys(("Sierra", "Emre", "Cassidy", "Soldier: 76"), 1.0),
    **dict.fromkeys(("Torbjörn", "Hanzo"), 0.0),
    **dict.fromkeys(
        (
            "Anran",
            "Bastion",
            "Genji",
            "Junkrat",
            "Mei",
            "Reaper",
            "Shion",
            "Sombra",
            "Symmetra",
            "Tracer",
            "Vendetta",
            "Venture",
            "Widowmaker",
        ),
        -2.0,
    ),
    "Winston": 1.0,  # Mercy × TANK
    "Ana": 2.0,  # Mercy × SUP
}
MERCY_ALLY_MATRIX = {
    "mercy": {scoring.normalize_hero_name(h): v for h, v in _MERCY_Y.items()},
    # Direção inversa (DPS candidato, Mercy no time) — assimétrica de propósito.
    "cassidy": {"mercy": 2.0},
}


def _mercy_syn(allies: list[str], preset: str = "equilibrado") -> float:
    return float(
        scoring.calculate_hero_score(
            "Mercy",
            MERCY_ALLY_MATRIX,
            {},
            allies,
            [],
            {},
            {},
            weights=scoring.resolve_weights(preset),
        )["synergy_score"]  # pyright: ignore[reportArgumentType]
    )


class TestMercyDpsSynergyWeight:
    """Par Mercy × DPS usa β = 1 (BETA_SYN_MERCY_DPS) nos QUATRO presets."""

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_peso_fixo_de_1_em_todos_os_presets(self, preset):
        # Y(Mercy, Cassidy) = 1 -> 1 × 1 = 1 (e não × β_syn do preset).
        assert _mercy_syn(["Cassidy"], preset) == pytest.approx(1.0)
        assert _mercy_syn(["Pharah"], preset) == pytest.approx(2.0)
        assert _mercy_syn(["Tracer"], preset) == pytest.approx(-2.0)

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_mercy_x_tank_e_mercy_x_sup_seguem_o_preset(self, preset):
        w = scoring.resolve_weights(preset)
        # Mercy × TANK: β_syn genérico do preset.
        assert _mercy_syn(["Winston"], preset) == pytest.approx(1.0 * w.beta_syn)
        # Mercy × SUP: a exceção SUP × SUP continua tendo precedência.
        beta_sup = w.beta_syn_sup_sup if w.beta_syn_sup_sup is not None else w.beta_syn
        assert _mercy_syn(["Ana"], preset) == pytest.approx(2.0 * beta_sup)

    def test_vale_tambem_com_o_dps_como_candidato(self):
        """O peso é do PAR: um DPS candidato com Mercy aliada também usa 1."""
        for preset in TODOS_OS_PRESETS:
            syn = float(
                scoring.calculate_hero_score(
                    "Cassidy",
                    MERCY_ALLY_MATRIX,
                    {},
                    ["Mercy"],
                    [],
                    {},
                    {},
                    weights=scoring.resolve_weights(preset),
                )["synergy_score"]  # pyright: ignore[reportArgumentType]
            )
            assert syn == pytest.approx(2.0), preset  # Y(Cassidy, Mercy) = 2

    def test_beta_syn_mercy_dps_definido_em_todos_os_presets(self):
        for preset in TODOS_OS_PRESETS:
            w = scoring.resolve_weights(preset)
            assert w.beta_syn_mercy_dps == scoring.BETA_SYN_MERCY_DPS == 1.0, preset


class TestMercyDpsPrioritario:
    """Com um DPS prioritário no time, só o de MAIOR Y(Mercy, ·) conta."""

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_time_1_sem_prioritario_soma_todos(self, preset):
        # Tracer (-2) + Hanzo (0): nenhum é prioritário -> nada é descartado.
        assert _mercy_syn(["Tracer", "Hanzo"], preset) == pytest.approx(-2.0)

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_time_2_prioritario_descarta_os_demais(self, preset):
        # Pharah (2, prioritário) + Tracer (-2): a Tracer é descartada.
        assert _mercy_syn(["Pharah", "Tracer"], preset) == pytest.approx(2.0)

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_time_3_empate_conta_um_so(self, preset):
        # Pharah e Ashe empatadas em 2: só uma conta (tanto faz qual).
        assert _mercy_syn(["Pharah", "Ashe"], preset) == pytest.approx(2.0)
        assert _mercy_syn(["Ashe", "Pharah"], preset) == pytest.approx(2.0)

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_time_4_vence_o_de_maior_valor(self, preset):
        # Cassidy (1) e Pharah (2), ambos prioritários: só a Pharah conta,
        # qualquer que seja a ordem do lineup.
        assert _mercy_syn(["Cassidy", "Pharah"], preset) == pytest.approx(2.0)
        assert _mercy_syn(["Pharah", "Cassidy"], preset) == pytest.approx(2.0)

    @pytest.mark.parametrize("preset", TODOS_OS_PRESETS)
    def test_time_sem_dps_aliado(self, preset):
        w = scoring.resolve_weights(preset)
        beta_sup = w.beta_syn_sup_sup if w.beta_syn_sup_sup is not None else w.beta_syn
        assert _mercy_syn([], preset) == pytest.approx(0.0)
        assert _mercy_syn(["Winston", "Ana"], preset) == pytest.approx(
            1.0 * w.beta_syn + 2.0 * beta_sup
        )

    def test_tank_e_sup_nao_sao_afetados_pela_regra(self):
        w = scoring.resolve_weights("equilibrado")
        # Pharah descarta a Tracer, mas Winston/Ana somam normalmente.
        esperado = 2.0 + 1.0 * w.beta_syn + 2.0 * w.beta_syn
        assert _mercy_syn(["Pharah", "Tracer", "Winston", "Ana"]) == pytest.approx(esperado)

    def test_todos_os_prioritarios_no_time(self):
        # 9 prioritários juntos: sobra só o topo (Pharah/Sojourn/Ashe/Freja/Echo = 2).
        prioritarios = [
            "Pharah",
            "Sojourn",
            "Ashe",
            "Freja",
            "Echo",
            "Sierra",
            "Emre",
            "Cassidy",
            "Soldier: 76",
        ]
        assert _mercy_syn(prioritarios) == pytest.approx(2.0)
        # Um prioritário de valor BAIXO ainda descarta os não-prioritários.
        assert _mercy_syn(["Cassidy", "Tracer", "Genji"]) == pytest.approx(1.0)

    def test_reasons_nao_citam_o_dps_descartado(self):
        r = scoring.calculate_hero_score(
            "Mercy", MERCY_ALLY_MATRIX, {}, ["Pharah", "Tracer"], [], {}, {}
        )
        reasons = r["reasons"]
        assert isinstance(reasons, list)
        assert any("Pharah" in motivo for motivo in reasons)
        assert not any("Tracer" in motivo for motivo in reasons)

    def test_a_regra_vale_so_para_a_mercy(self):
        """Outro SUP candidato soma todos os DPS aliados normalmente."""
        ally_matrix = {"ana": {"pharah": 2.0, "tracer": -2.0}}
        syn = float(
            scoring.calculate_hero_score("Ana", ally_matrix, {}, ["Pharah", "Tracer"], [], {}, {})[
                "synergy_score"
            ]  # pyright: ignore[reportArgumentType]
        )
        assert syn == pytest.approx((2.0 - 2.0) * scoring.BETA_SYN)

    def test_nao_afeta_o_enemy_threat(self):
        """Regressão: o threat weighting mantém a lógica própria (apply_mercy_pocket)."""
        syn = {
            "mercy": {"pharah": 2.0, "tracer": -2.0},
            "pharah": {"mercy": 2.0},
            "tracer": {"mercy": -2.0},
        }
        w = scoring.compute_threat_weights(
            ["Mercy", "Pharah", "Tracer"], {}, allies=[], synergy_matrix=syn
        )
        # Mercy × DPS continua somando na ameaça com o ν do preset (nada é
        # descartado lá); DPS × DPS é que é excluído. Depois vem o pocket.
        raw_mercy = scoring.NU_THREAT * (2.0 - 2.0)
        assert w["mercy"] == pytest.approx(
            scoring.threat_multiplier(raw_mercy) * scoring.MERCY_POCKET_MERCY_MULT
        )
        assert w["pharah"] == pytest.approx(
            scoring.threat_multiplier(scoring.NU_THREAT * 2.0) * scoring.MERCY_POCKET_DPS_MULT
        )
        assert w["tracer"] == pytest.approx(scoring.threat_multiplier(scoring.NU_THREAT * -2.0))


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
        # Colunas JÁ PONDERADAS: COUNTER = β_ctr·Σ w_e·C, META = β_meta·m,
        # SYNERGY = β_syn·Y — e TOTAL é a soma exata das três.
        assert r["counter_score"] == pytest.approx(scoring.BETA_CTR * (1.5 * 2.0 + 1.0 * (-1.0)))
        # diagonal (h com h) ignorada; só a1 conta
        assert r["synergy_score"] == pytest.approx(1.0 * scoring.BETA_SYN)  # 0.65
        assert r["meta_score"] == pytest.approx(scoring.BETA_META * 0.5)
        assert r["total"] == pytest.approx(
            r["meta_score"] + r["counter_score"] + r["synergy_score"]
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
