"""bump.py — Sincroniza a versão local do OWPick (tarefa 7.3).

Uso (a partir da raiz do repositório):

    python tools/bump.py 1.2.0

O que faz (apenas edição de arquivos — NÃO executa git):
  1. Valida o número de versão (formato semântico X.Y.Z).
  2. Grava a nova versão em ``version.txt`` (fonte única de versão).
  3. Garante um cabeçalho de seção correspondente no ``CHANGELOG.md``
     (``## [vX.Y.Z] — AAAA-MM-DD``), pronto para você preencher as notas.

O que NÃO faz (de propósito):
  - Não mexe em ``version.json``: esse arquivo é a fonte que o auto-updater lê,
    e quem o atualiza é o workflow de release (``.github/workflows/release.yml``),
    depois que o build e a Release existem — assim os usuários só veem a nova
    versão quando o artefato já está publicado.
  - Não cria commits nem tags. Você revisa as mudanças, faz o commit e cria a
    tag ``vX.Y.Z`` manualmente — é a tag que dispara o workflow.

Fluxo típico de release:
    python tools/bump.py 1.2.0        # atualiza version.txt + CHANGELOG
    # (edite o CHANGELOG com as notas da versão)
    git add -A && git commit -m "Release v1.2.0"
    git tag v1.2.0 && git push --tags   # <- dispara o GitHub Actions
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _validate(version: str) -> str:
    version = version.strip().lstrip("v")
    if not _SEMVER.match(version):
        raise SystemExit(f"Versão inválida: {version!r}. Use o formato X.Y.Z (ex.: 1.2.0).")
    return version


def _write_version_txt(version: str) -> None:
    VERSION_TXT.write_text(version + "\n", encoding="utf-8")
    print(f"[bump] version.txt -> {version}")


def _ensure_changelog_heading(version: str) -> None:
    if not CHANGELOG.exists():
        print("[bump] AVISO: CHANGELOG.md não encontrado — pulei a atualização do changelog.")
        return
    text = CHANGELOG.read_text(encoding="utf-8")
    if f"[v{version}]" in text:
        print(f"[bump] CHANGELOG.md já tem a seção v{version} (nada a fazer).")
        return
    today = _dt.date.today().isoformat()
    heading = f"## [v{version}] — {today}\n\n### (descreva as mudanças aqui)\n\n---\n\n"
    # Insere logo após o cabeçalho/introdução, antes da primeira seção de versão.
    marker = "\n## ["
    idx = text.find(marker)
    if idx == -1:
        new_text = text.rstrip() + "\n\n" + heading
    else:
        new_text = text[: idx + 1] + heading + text[idx + 1 :]
    CHANGELOG.write_text(new_text, encoding="utf-8")
    print(f"[bump] CHANGELOG.md: adicionado cabeçalho da v{version} ({today}).")


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("Uso: python tools/bump.py <X.Y.Z>")
    version = _validate(argv[1])
    _write_version_txt(version)
    _ensure_changelog_heading(version)
    print(
        "[bump] Pronto. Edite o CHANGELOG, faça o commit e crie a tag "
        f"'v{version}' para disparar o release."
    )


if __name__ == "__main__":
    main(sys.argv)
