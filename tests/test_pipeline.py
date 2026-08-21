"""Smoke test do pipeline.analyze — caminho paralelo OCR || matching (3.3)."""

import json
from pathlib import Path

from PIL import Image

from owpick import pipeline
from owpick.core.heroes import normalize_hero_name
from owpick.infra import capture

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _FakeGrab:
    def __init__(self, img):
        self.size = img.size
        self.rgb = img.convert("RGB").tobytes()


class _FakeSct:
    def __init__(self, img):
        self._img = img
        self.monitors = [{"a": 0}, {"b": 1}]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, _m):
        return _FakeGrab(self._img)


class _FakeMss:
    def __init__(self, img):
        self._img = img

    def mss(self):
        return _FakeSct(self._img)


def _norm(names):
    return [normalize_hero_name(n) for n in names]


def test_analyze_paralelo_reune_lineup_bans_mapa(tmp_path, monkeypatch):
    """analyze() roda OCR do mapa em paralelo ao matching e reúne tudo certo."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with Image.open(FIXTURES_DIR / "2k" / "full1.png") as img:
        img.load()
    monkeypatch.setattr(capture, "mss", _FakeMss(img))
    expected = json.loads((FIXTURES_DIR / "2k" / "expected.json").read_text(encoding="utf-8"))

    lineup, bans, detection = pipeline.analyze()

    assert _norm(lineup.ally_names()) == _norm(expected["allies"])
    assert _norm(lineup.enemy_names()) == _norm(expected["enemies"])
    assert _norm(bans.names()) == _norm(expected["bans"])
    assert normalize_hero_name(detection.name) == normalize_hero_name(expected["map"])
