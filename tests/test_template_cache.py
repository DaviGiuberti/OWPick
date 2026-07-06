"""Testes do cache de templates escalados (3.2)."""

from owpick.infra import matching


def test_load_all_templates_cacheado_por_chave():
    bank = matching.templates_base_dir / "2k"
    a = matching.load_all_templates(bank, (82, 82))
    b = matching.load_all_templates(bank, (82, 82))
    # Mesma (banco, template_size) -> MESMO objeto (cache hit, sem reler disco).
    assert a is b


def test_template_size_diferente_invalida_cache():
    bank = matching.templates_base_dir / "2k"
    a = matching.load_all_templates(bank, (82, 82))
    c = matching.load_all_templates(bank, (41, 41))
    # template_size diferente -> nova entrada (invalidação automática por chave).
    assert a is not c
    # E os arrays têm o tamanho pedido em cada caso.
    assert a["dps"][0][1].shape == (82, 82)
    assert c["dps"][0][1].shape == (41, 41)


def test_ban_templates_cacheado():
    bank = matching.templates_base_dir / matching.BAN_TEMPLATES_DIR_NAME
    a = matching.load_ban_templates(bank, matching.BAN_COMPARE_SIZE)
    b = matching.load_ban_templates(bank, matching.BAN_COMPARE_SIZE)
    assert a is b
