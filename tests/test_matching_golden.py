"""Golden tests do matching — o coração do produto.

Roda o pipeline REAL em memória (capture.capture -> matching -> map_detect.detect)
sobre capturas reais em tests/fixtures/<res>/ (full1.png nas três resoluções;
mais as fixtures adicionais full2/full3.png de 720p da v1.2.11, os JPEGs
full4.jpeg/full2.jpeg da v1.2.12 e o full2.jpg de 2K da v1.2.15), sem capturar a
tela: o `mss` é
substituído por um fake que devolve a imagem da fixture. Cada fixture tem um
gabarito expected*.json (lineup, bans, mapa); a comparação usa nomes
normalizados (core.heroes.normalize_hero_name).

Também mede e reporta a MARGEM (score do 1º vs 2º colocado) por slot do
lineup, para detectar degradação do matching antes que vire erro (rodar com
`pytest -s` para ver o relatório).
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from owpick import paths
from owpick.core.heroes import normalize_hero_name
from owpick.infra import capture, map_detect, matching

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESOLUTIONS = ["720p", "1080p", "2k"]

# Nome do arquivo da fixture por resolução: na v1.2.11 o full.png de 720p foi
# renomeado para full1.png (e ganhou os companheiros full2/full3.png), na
# v1.2.12 o mesmo aconteceu com o de 1080p (que ganhou o full2.jpeg) e na
# v1.2.15 com o de 2K (que ganhou o full2.jpg).
FIXTURE_FILE = {"720p": "full1.png", "1080p": "full1.png", "2k": "full1.png"}


class _FakeGrab:
    def __init__(self, img: Image.Image):
        self.size = img.size
        self.rgb = img.convert("RGB").tobytes()


class _FakeSct:
    """Substituto de mss.mss(): devolve a imagem da fixture no grab()."""

    def __init__(self, img: Image.Image):
        self._img = img
        self.monitors = [{"fake": "all"}, {"fake": "primary"}]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, _monitor):
        return _FakeGrab(self._img)


class _FakeMssModule:
    def __init__(self, img: Image.Image):
        self._img = img

    def mss(self):
        return _FakeSct(self._img)


def _norm(names):
    return [normalize_hero_name(n) for n in names]


def _capture_fixture(
    res: str, tmp_path, monkeypatch, fixture_file=None, expected_file="expected.json"
):
    """capture.capture() real sobre a imagem da fixture (mss falsificado)."""
    fixture = FIXTURES_DIR / res
    with Image.open(fixture / (fixture_file or FIXTURE_FILE[res])) as img:
        img.load()
    # Dados do usuário e cache isolados em tmp_path (sem Roles.txt) -> nenhum
    # slot de aliado é pulado (10 retratos). Aponta APPDATA/LOCALAPPDATA para o
    # tmp para não ler o %APPDATA% real da máquina.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(capture, "mss", _FakeMssModule(img))
    cap = capture.capture()
    expected = json.loads((fixture / expected_file).read_text(encoding="utf-8"))
    return cap, expected


@pytest.mark.parametrize("res", RESOLUTIONS)
def test_golden_lineup(res, tmp_path, monkeypatch):
    cap, expected = _capture_fixture(res, tmp_path, monkeypatch)
    lineup, slot_results = matching.match_lineup(cap)

    assert len(slot_results) == 10  # 5 aliados + 5 inimigos (sem Roles.txt)
    assert _norm(lineup.ally_names()) == _norm(expected["allies"]), (
        f"[{res}] aliados divergem: {lineup.ally_names()}"
    )
    assert _norm(lineup.enemy_names()) == _norm(expected["enemies"]), (
        f"[{res}] inimigos divergem: {lineup.enemy_names()}"
    )
    # A fronteira produz objetos Hero com role resolvida.
    assert all(h.role in ("DPS", "TANK", "SUP") for h in lineup.allies + lineup.enemies)


@pytest.mark.parametrize(
    "res",
    [
        "720p",
        pytest.param(
            "1080p",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Limite conhecido: em 1080p o slot do Wrecking Ball marca MAE "
                "0.152 > BAN_MATCH_MAX_SCORE (0.12, calibrado em 2K) e é descartado. "
                "Um slot VAZIO em 720p marca 0.173, então subir o limiar não resolve — "
                "requer critério de margem/métrica robusta (tarefas 4.1/4.2).",
            ),
        ),
        "2k",
    ],
)
def test_golden_bans(res, tmp_path, monkeypatch):
    cap, expected = _capture_fixture(res, tmp_path, monkeypatch)
    bans = matching.match_bans(cap)
    assert _norm(bans.names()) == _norm(expected["bans"]), f"[{res}] bans divergem: {bans.names()}"


# O antigo xfail do 720p (OCR ilegível, "Bh Pa") foi REMOVIDO na v1.2.0: a
# âncora 720p da região do mapa foi recalibrada no layout (890→1055; agora
# consistente com a âncora 2K ÷ 2) e o OCR passou a ler o nome corretamente
# (fixture Dorado: score 100). A recalibração também elevou o score do 1080p
# interpolado (39 → 67).
@pytest.mark.parametrize("res", RESOLUTIONS)
def test_golden_mapa(res, tmp_path, monkeypatch):
    cap, expected = _capture_fixture(res, tmp_path, monkeypatch)
    detection = map_detect.detect(cap.full)
    assert normalize_hero_name(detection.name) == normalize_hero_name(expected["map"]), (
        f"[{res}] mapa diverge: '{detection.name}'"
    )


# ---------------------------------------------------------------------------
# Fixtures 720p adicionais (v1.2.11): full2.png e full3.png
# ---------------------------------------------------------------------------

# (arquivo da fixture, gabarito) das capturas 720p adicionadas na v1.2.11.
EXTRA_720P = [
    ("full2.png", "expected2.json"),
    ("full3.png", "expected3.json"),
]


@pytest.mark.parametrize("fixture_file,expected_file", EXTRA_720P)
def test_golden_lineup_720p_extra(fixture_file, expected_file, tmp_path, monkeypatch):
    cap, expected = _capture_fixture("720p", tmp_path, monkeypatch, fixture_file, expected_file)
    lineup, slot_results = matching.match_lineup(cap)

    assert len(slot_results) == 10  # 5 aliados + 5 inimigos (sem Roles.txt)
    assert _norm(lineup.ally_names()) == _norm(expected["allies"]), (
        f"[{fixture_file}] aliados divergem: {lineup.ally_names()}"
    )
    assert _norm(lineup.enemy_names()) == _norm(expected["enemies"]), (
        f"[{fixture_file}] inimigos divergem: {lineup.enemy_names()}"
    )


@pytest.mark.parametrize("fixture_file,expected_file", EXTRA_720P)
def test_golden_mapa_720p_extra(fixture_file, expected_file, tmp_path, monkeypatch):
    cap, expected = _capture_fixture("720p", tmp_path, monkeypatch, fixture_file, expected_file)
    detection = map_detect.detect(cap.full)
    assert normalize_hero_name(detection.name) == normalize_hero_name(expected["map"]), (
        f"[{fixture_file}] mapa diverge: '{detection.name}'"
    )


# Limite conhecido dos bans fora de 2K (mesma causa do xfail do 1080p): nas duas
# fixtures o 4º ban legítimo marca MAE ACIMA do BAN_MATCH_MAX_SCORE (0.12,
# calibrado em 2K) e é descartado, embora seja o herói correto no topo do
# ranking — full2 (Wrecking Ball, MAE 0.152) e full3 (Mercy, MAE 0.141). O 5º
# slot está vazio e é corretamente rejeitado. O gabarito guarda os 4 bans reais
# da imagem; a detecção acha só 3 (requer critério de margem/métrica robusta,
# tarefas 4.1/4.2).
@pytest.mark.parametrize("fixture_file,expected_file", EXTRA_720P)
@pytest.mark.xfail(
    strict=True,
    reason="Limite conhecido: em 720p o 4º ban legítimo (Wrecking Ball 0.152 / "
    "Mercy 0.141) fica acima do BAN_MATCH_MAX_SCORE (0.12, calibrado em 2K) e é "
    "descartado — mesma causa do xfail do 1080p.",
)
def test_golden_bans_720p_extra(fixture_file, expected_file, tmp_path, monkeypatch):
    cap, expected = _capture_fixture("720p", tmp_path, monkeypatch, fixture_file, expected_file)
    bans = matching.match_bans(cap)
    assert _norm(bans.names()) == _norm(expected["bans"]), (
        f"[{fixture_file}] bans divergem: {bans.names()}"
    )


# ---------------------------------------------------------------------------
# Fixture 2K adicional (v1.2.15): full2.jpg
# ---------------------------------------------------------------------------
# Scoreboard de uma partida em Paraíso SEM bans (o gabarito guarda uma lista de
# bans vazia — os 5 slots são corretamente rejeitados). É a captura que expôs a
# falha do OCR do nome do jogador com nomes curtos: ver tests/test_player_hero.py.


def test_golden_lineup_2k_extra(tmp_path, monkeypatch):
    cap, expected = _capture_fixture("2k", tmp_path, monkeypatch, "full2.jpg", "expected2.json")
    lineup, slot_results = matching.match_lineup(cap)

    assert len(slot_results) == 10  # 5 aliados + 5 inimigos (sem Roles.txt)
    assert _norm(lineup.ally_names()) == _norm(expected["allies"]), (
        f"[2k/full2.jpg] aliados divergem: {lineup.ally_names()}"
    )
    assert _norm(lineup.enemy_names()) == _norm(expected["enemies"]), (
        f"[2k/full2.jpg] inimigos divergem: {lineup.enemy_names()}"
    )


def test_golden_bans_2k_extra(tmp_path, monkeypatch):
    """Partida sem bans: nenhum dos 5 slots pode virar um ban fantasma."""
    cap, expected = _capture_fixture("2k", tmp_path, monkeypatch, "full2.jpg", "expected2.json")
    bans = matching.match_bans(cap)
    assert _norm(bans.names()) == _norm(expected["bans"]), (
        f"[2k/full2.jpg] bans divergem: {bans.names()}"
    )


def test_golden_mapa_2k_extra(tmp_path, monkeypatch):
    cap, expected = _capture_fixture("2k", tmp_path, monkeypatch, "full2.jpg", "expected2.json")
    detection = map_detect.detect(cap.full)
    assert normalize_hero_name(detection.name) == normalize_hero_name(expected["map"]), (
        f"[2k/full2.jpg] mapa diverge: '{detection.name}'"
    )


# ---------------------------------------------------------------------------
# A MESMA partida em três capturas (v1.2.12 / v1.2.13)
# ---------------------------------------------------------------------------
# 720p/full4.jpeg, 1080p/full2.jpeg e 1080p/full3.png são a mesma tela de seleção
# (D.Va, Soldier: 76, Torbjörn, Juno, Kiriko vs D.Va, Soldier: 76, Cassidy,
# Kiriko, Ana em New Queen Street). As duas primeiras são as PRIMEIRAS fixtures em
# JPEG (as demais são PNG). Juntas cobrem resolução (720p vs 1080p) e formato
# (JPEG com perdas vs PNG) sobre um conteúdo idêntico — cada uma expôs um jeito
# diferente de o OCR do nome do herói errar (ver tests/test_player_hero.py).
JPEG_FIXTURES = [
    ("720p", "full4.jpeg", "expected4.json"),
    ("1080p", "full2.jpeg", "expected2.json"),
    ("1080p", "full3.png", "expected3.json"),
]


@pytest.mark.parametrize("res,fixture_file,expected_file", JPEG_FIXTURES)
def test_golden_lineup_jpeg(res, fixture_file, expected_file, tmp_path, monkeypatch):
    cap, expected = _capture_fixture(res, tmp_path, monkeypatch, fixture_file, expected_file)
    lineup, slot_results = matching.match_lineup(cap)

    assert len(slot_results) == 10  # 5 aliados + 5 inimigos (sem Roles.txt)
    assert _norm(lineup.ally_names()) == _norm(expected["allies"]), (
        f"[{res}/{fixture_file}] aliados divergem: {lineup.ally_names()}"
    )
    assert _norm(lineup.enemy_names()) == _norm(expected["enemies"]), (
        f"[{res}/{fixture_file}] inimigos divergem: {lineup.enemy_names()}"
    )


@pytest.mark.parametrize("res,fixture_file,expected_file", JPEG_FIXTURES)
def test_golden_mapa_jpeg(res, fixture_file, expected_file, tmp_path, monkeypatch):
    cap, expected = _capture_fixture(res, tmp_path, monkeypatch, fixture_file, expected_file)
    detection = map_detect.detect(cap.full)
    assert normalize_hero_name(detection.name) == normalize_hero_name(expected["map"]), (
        f"[{res}/{fixture_file}] mapa diverge: '{detection.name}'"
    )


@pytest.mark.parametrize(
    "fixture_file,expected_file",
    [("full2.jpeg", "expected2.json"), ("full3.png", "expected3.json")],
)
def test_golden_bans_1080p_mesma_partida(fixture_file, expected_file, tmp_path, monkeypatch):
    """Em 1080p os 4 bans da captura são detectados corretamente."""
    cap, expected = _capture_fixture("1080p", tmp_path, monkeypatch, fixture_file, expected_file)
    bans = matching.match_bans(cap)
    assert _norm(bans.names()) == _norm(expected["bans"]), (
        f"[{fixture_file}] bans divergem: {bans.names()}"
    )


# Mesmo limite conhecido dos demais bans fora de 2K: em 720p o slot do Bastion
# marca MAE 0.1348 > BAN_MATCH_MAX_SCORE (0.12, calibrado em 2K) e é descartado,
# embora seja o herói correto no topo do ranking. O 5º slot (vazio) marca 0.1924,
# então subir o limiar para acomodar 0.135 encosta demais no ruído — a correção
# exige critério de margem/métrica robusta (tarefas 4.1/4.2), não recalibração.
# A MESMA captura em 1080p (full2.jpeg) acerta os 4 bans, o que confirma que a
# causa é a resolução do ícone, não o JPEG.
@pytest.mark.xfail(
    strict=True,
    reason="Limite conhecido: em 720p o ban do Bastion marca MAE 0.1348 > "
    "BAN_MATCH_MAX_SCORE (0.12) e é descartado — mesma causa dos xfails de "
    "full2/full3.png e do 1080p da v1.2.11.",
)
def test_golden_bans_jpeg_720p(tmp_path, monkeypatch):
    cap, expected = _capture_fixture("720p", tmp_path, monkeypatch, "full4.jpeg", "expected4.json")
    bans = matching.match_bans(cap)
    assert _norm(bans.names()) == _norm(expected["bans"]), f"bans divergem: {bans.names()}"


# ---------------------------------------------------------------------------
# Limiar de confiança do lineup (tarefa 4.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("res", RESOLUTIONS)
def test_lineup_slots_reais_sao_confiantes(res, tmp_path, monkeypatch):
    """Calibração: todos os 10 slots das capturas reais ficam ABAIXO do limiar
    (nenhum match legítimo é rejeitado por engano)."""
    cap, _expected = _capture_fixture(res, tmp_path, monkeypatch)
    _lineup, slot_results = matching.match_lineup(cap)
    for slot, mr in slot_results.items():
        assert mr.confident, (
            f"[{res}] {slot} rejeitado indevidamente: score={mr.score:.4f} "
            f"> {matching.LINEUP_MATCH_MAX_SCORE}"
        )


def test_lineup_slot_lixo_e_rejeitado(tmp_path, monkeypatch):
    """Um slot substituído por ruído (sem retrato) vira NÃO identificado e é
    excluído do lineup — elimina a recomendação sobre lineup fictício."""
    cap, _expected = _capture_fixture("2k", tmp_path, monkeypatch)
    # Branco sólido: distante de qualquer retrato (que tem áreas escuras), então
    # o melhor score fica bem acima do limiar — exercita o caminho de rejeição.
    for crops in cap.portraits.values():
        if "enemy3.png" in crops:
            crops["enemy3.png"] = Image.new("RGB", (44, 60), (255, 255, 255))

    lineup, slot_results = matching.match_lineup(cap)
    assert not slot_results["enemy3.png"].confident
    assert slot_results["enemy3.png"].hero is None
    # O slot de lixo não entra na lista de inimigos (fica com 4 em vez de 5).
    assert len(lineup.enemies) == 4


# ---------------------------------------------------------------------------
# Fluxo CLI por arquivos (compatibilidade) — mesma implementação de matching
# ---------------------------------------------------------------------------


def test_fluxo_cli_por_arquivos_equivalente(tmp_path, monkeypatch):
    """save_debug_artifacts + executar() (arquivos) reproduz o resultado em memória."""
    cap, expected = _capture_fixture("2k", tmp_path, monkeypatch)
    capture.save_debug_artifacts(cap)

    matching.executar()  # lê cache/print/, escreve cache/lineup.txt e bans.txt
    lines = Path(paths.cache_file("lineup.txt")).read_text(encoding="utf-8").splitlines()
    lineup_names = [line for line in lines if line.strip()]
    assert _norm(lineup_names[:5]) == _norm(expected["allies"])
    assert _norm(lineup_names[5:10]) == _norm(expected["enemies"])

    mapa = map_detect.executar()  # lê cache/print/full.png, escreve current_map.txt
    assert normalize_hero_name(mapa) == normalize_hero_name(expected["map"])
    assert Path(paths.cache_file("current_map.txt")).read_text(encoding="utf-8") == mapa


# ---------------------------------------------------------------------------
# Margem por slot (1º vs 2º colocado) — relatório de saúde do matching
# ---------------------------------------------------------------------------


def _slot_margins(res: str, tmp_path, monkeypatch):
    """Para cada slot do lineup, calcula (melhor, segundo) score de matching."""
    cap, _expected = _capture_fixture(res, tmp_path, monkeypatch)
    templates_by_category, crop_size, window_height = matching.lineup_templates_for(cap)

    # Usa a melhor variação de perk (mesmo critério do match_lineup).
    stats = []
    for perk_name, crops in cap.portraits.items():
        results = matching._match_slots(crops, templates_by_category, crop_size, window_height)
        if results:
            avg = sum(r[2] for r in results) / len(results)
            stats.append((avg, perk_name))
    best_perk = min(stats)[1]

    margins = {}
    for slot_name in sorted(cap.portraits[best_perk]):
        category = matching.FILE_TO_CATEGORY.get(slot_name)
        if category is None:
            continue
        img_arr = matching.to_gray_array(cap.portraits[best_perk][slot_name])
        scores = []
        for name, tpl in templates_by_category[category]:
            _n, score = matching.find_best_match_sliding(
                img_arr, [(name, tpl)], window_height, crop_size[0]
            )
            scores.append((score, name))
        scores.sort()
        (s1, n1), (s2, _n2) = scores[0], scores[1]
        margins[slot_name] = (n1, s1, s2 - s1)
    return margins


@pytest.mark.parametrize("res", RESOLUTIONS)
def test_margem_por_slot_positiva(res, tmp_path, monkeypatch):
    margins = _slot_margins(res, tmp_path, monkeypatch)
    assert margins, f"[{res}] nenhum slot processado"
    print(f"\n[{res}] margem por slot (1º vs 2º colocado):")
    for slot, (name, score, margin) in margins.items():
        print(f"  {slot:<12} {name:<16} score={score:.4f}  margem={margin:.4f}")
    for slot, (_name, _score, margin) in margins.items():
        assert margin > 0.0, f"[{res}] {slot}: empate entre 1º e 2º colocado"
