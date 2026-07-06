"""Aliases de mapa por idioma (tarefa 4.6)."""

from __future__ import annotations

import pytest

from owpick.core.heroes import MAP_ALIASES, get_map_names, get_map_search_index
from owpick.infra import map_detect


def test_indice_inclui_canonicos_e_aliases():
    index = get_map_search_index()
    # todo canônico aponta para si mesmo
    for name in get_map_names():
        assert index[name] == name
    # todo alias aponta para o canônico
    for canonical, per_lang in MAP_ALIASES.items():
        for alias in per_lang.values():
            assert index[alias] == canonical


def test_aliases_referenciam_mapas_reais():
    """Nenhum alias aponta para um mapa que não existe (evita typo silencioso)."""
    names = set(get_map_names())
    for canonical in MAP_ALIASES:
        assert canonical in names, f"alias para mapa inexistente: {canonical!r}"


@pytest.mark.parametrize(
    ("ocr", "canonical"),
    [
        ("Rota 66", "Route 66"),
        ("Monastério Shambali", "Shambali Monastery"),
        ("Península Antártica", "Antarctic Peninsula"),
        # com ruído de UI ao redor (como o OCR real entrega)
        ("COMPETITIVE | Rota 66", "Route 66"),
    ],
)
def test_ocr_ptbr_resolve_para_canonico(ocr, canonical):
    name, score = map_detect.identify_map(ocr)
    assert name == canonical
    assert score >= map_detect.MIN_CONFIDENCE


def test_ocr_ingles_ainda_funciona():
    name, _score = map_detect.identify_map("NEON JUNCTION")
    assert name == "Neon Junction"
