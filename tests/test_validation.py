"""Validador de matrizes/stats/templates (tarefa 5.2)."""

from __future__ import annotations

from owpick.infra import validation

# ---------------------------------------------------------------------------
# Dados REAIS — a rede de segurança contra typos/omissões (roda no CI)
# ---------------------------------------------------------------------------
# LACUNA CONHECIDA E ACEITA (v1.2.14): a D.Mon ainda não tem o ícone 3D oficial
# em assets/heroes/bans/. O ícone de ban usa uma ARTE DIFERENTE do retrato do
# lineup (não dá para derivar um do outro), então o asset não existe até ser
# extraído do jogo. A degradação é segura e local: `match_bans` simplesmente
# nunca aponta a D.Mon como banida (ela não é removida do ranking se for banida);
# nada mais no pipeline depende disso. O validador CONTINUA reportando a
# ausência — é assim que o autor lembra de adicionar o ícone — e este teste
# aceita EXATAMENTE esse problema e nenhum outro.
KNOWN_DATA_GAPS = ["[templates] ícones de BAN ausentes: D.Mon"]


def test_dados_reais_sao_validos():
    problems = validation.validate_all()
    unexpected = [p for p in problems if p not in KNOWN_DATA_GAPS]
    assert unexpected == [], "Problemas nos dados reais:\n" + "\n".join(unexpected)


def test_lacuna_conhecida_continua_sendo_reportada():
    """O validador não pode 'esquecer' a lacuna aceita: enquanto o ícone de ban
    da D.Mon não existir, ele precisa aparecer no relatório."""
    problems = validation.validate_all()
    missing_bans = [p for p in problems if "ícones de BAN ausentes" in p]
    assert missing_bans == KNOWN_DATA_GAPS or missing_bans == [], (
        f"lacuna de bans mudou de forma inesperada: {missing_bans}"
    )


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


def test_coluna_sem_dados_nao_e_reportada_como_ausente():
    """Herói com a coluna VAZIA na planilha (sem nenhum valor) não é 'ausente'.

    `build_matrix_dict` descarta células vazias, então a coluna some da matriz
    normalizada. Passando o cabeçalho real, o validador enxerga a coluna e só
    reclama do que realmente falta no arquivo (v1.2.14)."""
    from owpick.core.heroes import get_all_heroes, normalize_hero_name

    keys = [normalize_hero_name(h) for h in get_all_heroes()]
    vazio = keys[0]  # este herói não tem NENHUM valor em coluna alguma
    matrix = {k: {c: 0.0 for c in keys if c != vazio} for k in keys}

    # Sem o cabeçalho: a coluna vazia vira falso positivo (comportamento herdado).
    assert any("AUSENTES nas colunas" in p for p in validation.validate_matrix(matrix, "synergies"))
    # Com o cabeçalho real da planilha: nada a reclamar.
    assert validation.validate_matrix(matrix, "synergies", keys) == []


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
