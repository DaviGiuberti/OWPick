"""Testes de tools/bump.py (sincronização de versão — tarefa 7.3)."""

import importlib.util
from pathlib import Path

import pytest

_BUMP_PATH = Path(__file__).resolve().parent.parent / "tools" / "bump.py"
_spec = importlib.util.spec_from_file_location("owpick_bump", _BUMP_PATH)
assert _spec and _spec.loader
bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump)


def test_valida_semver():
    assert bump._validate("1.2.0") == "1.2.0"
    assert bump._validate("v1.2.0") == "1.2.0"
    with pytest.raises(SystemExit):
        bump._validate("1.2")
    with pytest.raises(SystemExit):
        bump._validate("abc")


def test_escreve_version_txt(monkeypatch, tmp_path):
    vt = tmp_path / "version.txt"
    monkeypatch.setattr(bump, "VERSION_TXT", vt)
    bump._write_version_txt("1.2.0")
    assert vt.read_text(encoding="utf-8").strip() == "1.2.0"


def test_insere_cabecalho_no_changelog(monkeypatch, tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\nIntro.\n\n---\n\n## [v1.1.6] — 2026-07-03\n\nold\n", "utf-8")
    monkeypatch.setattr(bump, "CHANGELOG", cl)
    bump._ensure_changelog_heading("1.2.0")
    text = cl.read_text(encoding="utf-8")
    assert "[v1.2.0]" in text
    # A nova seção vem antes da anterior.
    assert text.index("[v1.2.0]") < text.index("[v1.1.6]")


def test_nao_duplica_secao_existente(monkeypatch, tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [v1.2.0] — 2026-07-05\n\nx\n", "utf-8")
    monkeypatch.setattr(bump, "CHANGELOG", cl)
    bump._ensure_changelog_heading("1.2.0")
    assert cl.read_text(encoding="utf-8").count("[v1.2.0]") == 1
