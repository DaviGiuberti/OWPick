"""Validador de matrizes/stats/templates (tarefa 5.2)."""

from __future__ import annotations

from owpick.infra import validation


# ---------------------------------------------------------------------------
# Dados REAIS — a rede de segurança contra typos/omissões (roda no CI)
# ---------------------------------------------------------------------------
def test_dados_reais_sao_validos():
    problems = validation.validate_all()
    assert problems == [], "Problemas nos dados reais:\n" + "\n".join(problems)


# ---------------------------------------------------------------------------
# Casos sintéticos — o validador detecta o que deveria
# ---------------------------------------------------------------------------
def test_matriz_detecta_orfao_e_ausente():
    from owpick.core.heroes import get_all_heroes, normalize_hero_name

    keys = [normalize_hero_name(h) for h in get_all_heroes()]
    # tira um herói e injeta um typo órfão
    keys = keys[1:] + ["rroadhog"]
    matrix = {k: {c: 0.0 for c in keys} for k in keys}
    problems = validation.validate_matrix(matrix, "counters")
    joined = " ".join(problems)
    assert "AUSENTES" in joined
    assert "ÓRFÃS" in joined and "rroadhog" in joined


def test_templates_detecta_ausencia(tmp_path):
    # Diretório vazio: todos os retratos e bans faltam.
    problems = validation.validate_templates(tmp_path)
    joined = " ".join(problems)
    assert "retratos de lineup AUSENTES" in joined
    assert "ícones de BAN ausentes" in joined


def test_report_problems_ok_e_com_erros():
    out: list[str] = []
    assert validation.report_problems([], echo=out.append) is True
    out.clear()
    assert validation.report_problems(["[x] algo errado"], echo=out.append) is False
    assert any("PROBLEMA" in line for line in out)
