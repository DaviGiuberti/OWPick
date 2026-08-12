"""Testes unitários de core.heroes / core.resolution — funções puras, sem I/O."""

import pandas as pd
import pytest

from owpick.core import heroes, resolution
from owpick.core.heroes import build_matrix_dict, normalize_hero_name
from owpick.core.resolution import (
    get_scaled_map_region,
    pick_template_bank,
    template_bank_for_resolution,
)
from owpick.infra import datasource

# ---------------------------------------------------------------------------
# normalize_hero_name
# ---------------------------------------------------------------------------


class TestNormalizeHeroName:
    def test_dva_equivalence(self):
        assert normalize_hero_name("D.Va") == normalize_hero_name("DVa") == "dva"

    def test_soldier_equivalence(self):
        assert (
            normalize_hero_name("Soldier: 76") == normalize_hero_name("Soldier 76") == "soldier-76"
        )

    def test_accents(self):
        assert normalize_hero_name("Lúcio") == "lucio"
        assert normalize_hero_name("Torbjörn") == "torbjorn"

    def test_none_and_empty(self):
        assert normalize_hero_name(None) == ""  # pyright: ignore[reportArgumentType]
        assert normalize_hero_name("") == ""

    def test_all_heroes_have_unique_keys(self):
        all_heroes = heroes.get_all_heroes()
        keys = {normalize_hero_name(h) for h in all_heroes}
        assert len(keys) == len(all_heroes) == 53


# ---------------------------------------------------------------------------
# build_matrix_dict
# ---------------------------------------------------------------------------


class TestBuildMatrixDict:
    def test_normalizes_rows_and_columns_and_skips_nan(self):
        df = pd.DataFrame(
            {"Soldier: 76": [1.5, float("nan")], "Lúcio": [-2.0, 0.5]},
            index=["D.Va", "Mei"],
        )
        result = build_matrix_dict(df)
        assert result == {
            "dva": {"soldier-76": 1.5, "lucio": -2.0},
            "mei": {"lucio": 0.5},  # NaN de Soldier: 76 é descartado
        }


# ---------------------------------------------------------------------------
# pick_template_bank / template_bank_for_resolution
# ---------------------------------------------------------------------------


class TestPickTemplateBank:
    def test_720p_portrait(self):
        assert pick_template_bank(41.0) == "720p"

    def test_midpoint_tie_prefers_2k(self):
        # 61.5px é equidistante de 41 (720p) e 82 (2k) — desempate: maior banco.
        assert pick_template_bank(61.5) == "2k"

    def test_2k_portrait(self):
        assert pick_template_bank(82.0) == "2k"

    def test_1080p_resolution_uses_2k_bank(self):
        # Em 1080p o retrato fica ~61.5px -> banco 2k (empate resolvido p/ 2k).
        assert template_bank_for_resolution(1920) == "2k"

    def test_720p_and_2k_resolutions(self):
        assert template_bank_for_resolution(1280) == "720p"
        assert template_bank_for_resolution(2560) == "2k"


# ---------------------------------------------------------------------------
# get_scaled_map_region — âncoras reais do layout do projeto
# (data/layouts/ow_hero_select.json; a âncora 720p foi RECALIBRADA na v1.2.0 —
# a antiga (890, 17, 113, 21) não cobria o nome do mapa e o OCR lia lixo)
# ---------------------------------------------------------------------------

CONFIG = {
    "2k": {
        "map_region": {"left": 2104, "top": 38, "width": 269, "height": 50},
        "base_resolution": {"width": 2560, "height": 1440},
    },
    "720p": {
        "map_region": {"left": 1055, "top": 16, "width": 131, "height": 31},
        "base_resolution": {"width": 1280, "height": 720},
    },
}


class TestGetScaledMapRegion:
    def test_720p_anchor_exact(self):
        assert get_scaled_map_region(1280, 720, CONFIG) == (1055, 16, 1186, 47)

    def test_2k_anchor_exact(self):
        assert get_scaled_map_region(2560, 1440, CONFIG) == (2104, 38, 2373, 88)

    def test_1080p_interpolated_midpoint(self):
        # t = (1920-1280)/(2560-1280) = 0.5 -> média das âncoras em cada coord.
        region = get_scaled_map_region(1920, 1080, CONFIG)
        assert region is not None
        left, top, right, bottom = region
        assert left == round((1055 + 2104) / 2) == 1580
        assert right - left == round((131 + 269) / 2) == 200
        assert top == round((16 + 38) / 2)
        assert bottom - top == round((31 + 50) / 2)

    def test_4k_extrapolated_from_2k(self):
        # Fora do intervalo: escala proporcional a partir da âncora mais próxima.
        region = get_scaled_map_region(3840, 2160, CONFIG)
        assert region is not None
        left, top, right, bottom = region
        assert left == round(2104 * 1.5)
        assert top == round(38 * 1.5)
        assert right - left == round(269 * 1.5)
        assert bottom - top == round(50 * 1.5)

    def test_region_always_inside_image(self):
        for w, h in [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160), (1600, 900)]:
            region = get_scaled_map_region(w, h, CONFIG)
            assert region is not None
            left, top, right, bottom = region
            assert 0 <= left < right <= w
            assert 0 <= top < bottom <= h

    def test_empty_config_returns_none(self):
        assert get_scaled_map_region(1920, 1080, {}) is None

    def test_real_config_json_matches_constants(self):
        # O layout do repositório deve produzir as mesmas âncoras deste teste
        # (pin da calibração vigente — validada pelos golden tests de mapa).
        real = datasource.load_capture_config()
        assert get_scaled_map_region(1280, 720, real) == (1055, 16, 1186, 47)
        assert get_scaled_map_region(2560, 1440, real) == (2104, 38, 2373, 88)


# ---------------------------------------------------------------------------
# Constantes canônicas — contagens oficiais
# ---------------------------------------------------------------------------


class TestCanonicalData:
    def test_hero_counts(self):
        assert len(heroes.HEROES_ROLES["DPS"]) == 24
        assert len(heroes.HEROES_ROLES["TANK"]) == 15  # +D.Mon (v1.2.14)
        assert len(heroes.HEROES_ROLES["SUP"]) == 14

    def test_map_count(self):
        assert len(heroes.MAPS_DATA) == 29

    def test_neutral_pickrates(self):
        pr = heroes.get_role_neutral_pickrates()
        assert pr["DPS"] == pytest.approx(2 / 24)
        assert pr["TANK"] == pytest.approx(1 / 15)
        assert pr["SUP"] == pytest.approx(2 / 14)


# ---------------------------------------------------------------------------
# resolution.resolution_scale / nearest_resolution_key
# ---------------------------------------------------------------------------


class TestResolutionHelpers:
    def test_scale(self):
        assert resolution.resolution_scale(1280) == 1.0
        assert resolution.resolution_scale(2560) == 2.0

    def test_nearest_key_tie_prefers_larger(self):
        # 1080p equidistante de 720p e 2K -> maior resolução (2k).
        assert resolution.nearest_resolution_key(1920, 1080) == "2k"
