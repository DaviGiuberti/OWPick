"""Testes do layout de captura versionado (data/layouts/ow_hero_select.json, 2.7)."""

from owpick.core import resolution
from owpick.infra import datasource


def test_layout_carrega_e_tem_secoes():
    layout = datasource.load_layout()
    assert layout.get("version") == 1
    assert layout["base_resolution"] == {"width": 1280, "height": 720}
    # 10 slots de lineup (5 aliados + 5 inimigos) e 4 variações de perk.
    assert len(layout["lineup"]["slots"]) == 10
    assert [p["name"] for p in layout["lineup"]["perks"]] == ["0perk", "1perk", "bug", "2perk"]
    assert len(layout["bans"]["slots"]) == 5


def test_load_capture_config_deriva_ancoras_do_mapa():
    """load_capture_config extrai as âncoras do mapa do layout (forma antiga)."""
    cfg = datasource.load_capture_config()
    # Pin da calibração vigente do layout. A âncora 720p foi RECALIBRADA na
    # v1.2.0 (a antiga 890,17,113,21 não cobria o nome do mapa — OCR lia lixo);
    # a nova é consistente com a âncora 2K (~2K/2) e é validada empiricamente
    # pelos golden tests de mapa (720p/1080p/2K).
    assert resolution.get_scaled_map_region(1280, 720, cfg) == (1055, 16, 1186, 47)
    assert resolution.get_scaled_map_region(2560, 1440, cfg) == (2104, 38, 2373, 88)


def test_crop_capture_usa_geometria_do_layout(monkeypatch, tmp_path):
    """Sem Roles.txt, todos os 10 slots são recortados nas 4 perks."""
    from PIL import Image

    from owpick.infra import capture

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    img = Image.new("RGB", (1280, 720), (30, 30, 30))
    cap = capture.crop_capture(img, role=None)
    assert set(cap.portraits) == {"0perk", "1perk", "bug", "2perk"}
    assert len(cap.portraits["0perk"]) == 10
    assert len(cap.bans) == 5
