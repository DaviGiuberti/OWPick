"""Testes da detecção automática do herói/role do jogador (v1.2.10).

Cobre o módulo infra/player_hero (OCR do nome + fuzzy match + role) sobre as
capturas reais em tests/fixtures/<res>/full1.png, o fallback quando não há herói
legível, o escalonamento da região por resolução e a integração no pipeline
(role detectada tem prioridade sobre a role manual, com fallback ao Roles.txt).
"""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from owpick import pipeline
from owpick.core.heroes import get_all_heroes, normalize_hero_name
from owpick.infra import capture, ocr_backends, player_hero, storage

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESOLUTIONS = ["720p", "1080p", "2k"]

# Nome do arquivo da fixture por resolução (v1.2.11: 720p/full.png -> full1.png;
# v1.2.12: 1080p/full.png -> full1.png; v1.2.15: 2k/full.png -> full1.png).
FIXTURE_FILE = {"720p": "full1.png", "1080p": "full1.png", "2k": "full1.png"}

# Herói que o JOGADOR está usando em cada captura (retrato/nome grande na
# scoreboard) — distinto do gabarito de lineup em expected.json.
PLAYER_HERO = {"720p": ("Sierra", "DPS"), "1080p": ("Reaper", "DPS"), "2k": ("Hanzo", "DPS")}


class _FakeGrab:
    def __init__(self, img):
        self.size = img.size
        self.rgb = img.convert("RGB").tobytes()


class _FakeSct:
    def __init__(self, img):
        self._img = img
        self.monitors = [{"all": 0}, {"primary": 1}]

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


def _load_full(res: str) -> Image.Image:
    with Image.open(FIXTURES_DIR / res / FIXTURE_FILE[res]) as img:
        img.load()
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Detecção sobre capturas reais
# ---------------------------------------------------------------------------
def test_detecta_heroi_e_role_do_jogador_nas_fixtures():
    for res in RESOLUTIONS:
        hero_name, role = PLAYER_HERO[res]
        hero = player_hero.detect(_load_full(res))
        assert hero is not None, f"[{res}] herói do jogador não identificado"
        assert hero.key == normalize_hero_name(hero_name), f"[{res}] herói divergiu: {hero.name}"
        assert hero.role == role, f"[{res}] role divergiu: {hero.role}"


def test_regiao_do_nome_escala_com_a_resolucao():
    # A região é definida na base 720p; em 2K (2x) deve ficar ~2x maior e dentro
    # dos limites da imagem — o mesmo mecanismo de escala dos demais recortes.
    box_720 = player_hero.name_region(1280, 720)
    box_2k = player_hero.name_region(2560, 1440)
    assert box_720 == (789, 238, 919, 277)
    left, top, right, bottom = box_2k
    assert (left, top) == (1578, 476)
    assert right <= 2560 and bottom <= 1440
    # Largura/altura aproximadamente o dobro da base.
    assert abs((right - left) - 2 * (919 - 789)) <= 2
    assert abs((bottom - top) - 2 * (277 - 238)) <= 2


# ---------------------------------------------------------------------------
# Fuzzy match do nome
# ---------------------------------------------------------------------------
def test_identify_hero_tolerante_a_ruido_e_acentos():
    # Ruído do badge de role ao lado do nome (como nas capturas reais).
    assert player_hero.identify_hero("SIERRA &")[0] == "Sierra"
    assert player_hero.identify_hero("HANZO @")[0] == "Hanzo"
    # Sem acento/pontuação (como o OCR normalmente lê).
    assert player_hero.identify_hero("LUCIO")[0] == "Lúcio"
    assert player_hero.identify_hero("TORBJORN")[0] == "Torbjörn"
    assert player_hero.identify_hero("SOLDIER 76")[0] == "Soldier: 76"


def test_identify_hero_texto_vazio_nao_casa():
    assert player_hero.identify_hero("") == ("", 0.0)


# ---------------------------------------------------------------------------
# Regressão v1.2.12 / v1.2.13: D.Va não era reconhecida
# ---------------------------------------------------------------------------
# A região do nome inclui o BADGE de role, e ele estraga o OCR de DUAS formas
# diferentes — cada uma pegou uma fixture e cada uma exigiu uma correção:
#
#   1. (v1.2.12) O badge é lido COLADO ao nome e o Tesseract não enxerga o ponto
#      de "D.Va": em 720p/full4.jpeg o OCR devolve "DVS". Contra o nome canônico
#      COM pontuação isso dava 57.1 -> _strip_upper passou a descartar a
#      pontuação dos dois lados.
#   2. (v1.2.13) O badge é lido como um TOKEN SEPARADO e o "D" sai como "O": em
#      1080p/full3.png o OCR devolve "OVA &". O token "&" infla o comprimento da
#      frase e derruba o token_set_ratio para 50.0 -> _strip_upper passou a
#      descartar tokens sem nenhum alfanumérico.
#
# Nos dois casos a falha era SILENCIOSA: o herói caía abaixo de MIN_CONFIDENCE, o
# pipeline usava a role manual (Roles.txt) e o ranking saía para a role errada.
# Nenhuma das correções é um caso especial da D.Va.

# (fixture, texto que o OCR realmente produz) das três capturas da mesma partida.
DVA_OCR_READS = [
    ("720p/full4.jpeg", "DVS"),  # badge colado + ponto perdido
    ("1080p/full2.jpeg", "D.VA"),  # leitura limpa
    ("1080p/full3.png", "OVA &"),  # badge separado + D lido como O
]


@pytest.mark.parametrize("origem,ocr_text", DVA_OCR_READS)
def test_dva_reconhecida_apesar_do_ruido_do_badge(origem, ocr_text):
    """O texto que o OCR realmente produz nessas capturas casa com D.Va."""
    name, score = player_hero.identify_hero(ocr_text)
    assert name == "D.Va", f"[{origem}] OCR {ocr_text!r} casou com {name!r}"
    assert score >= player_hero.MIN_CONFIDENCE, (
        f"[{origem}] score {score:.1f} < limiar {player_hero.MIN_CONFIDENCE}"
    )


@pytest.mark.parametrize(
    "res,fixture_file",
    [("720p", "full4.jpeg"), ("1080p", "full2.jpeg"), ("1080p", "full3.png")],
)
def test_detecta_dva_nas_fixtures_da_mesma_partida(res, fixture_file):
    """detect() ponta a ponta: as três capturas da partida devolvem D.Va/TANK."""
    with Image.open(FIXTURES_DIR / res / fixture_file) as img:
        img.load()
    hero = player_hero.detect(img.convert("RGB"))
    assert hero is not None, f"[{res}/{fixture_file}] herói do jogador não identificado"
    assert hero.key == normalize_hero_name("D.Va")
    assert hero.role == "TANK"


# ---------------------------------------------------------------------------
# Regressão v1.2.15: nome CURTO ilegível para o pré-processo padrão (Mei)
# ---------------------------------------------------------------------------
# Terceiro modo de falha da mesma família — e o primeiro que NÃO é do fuzzy match.
# Em 2k/full2.jpg (jogador de Mei) o pré-processo padrão (autocontraste GLOBAL do
# recorte) devolve "" — string vazia, nenhum caractere. Não é o badge estragando o
# score: o Tesseract simplesmente não acha texto. Medido antes da correção, o
# recorte lia "" com todos os psm de linha (3/6/7/11/12), com e sem dicionário
# (load_system_dawg=0), com e sem whitelist de caracteres e nos dois engines
# (--oem 1 e 3). A causa é a binarização: o recorte é quase todo preto (88% dos
# pixels ficam abaixo de 38 depois do autocontraste) porque o autocontraste global
# é puxado pelo ponto mais brilhante — o badge de role — e as hastes finas do nome
# em itálico continuam cinza.
#
# A falha era SILENCIOSA e reproduzia o mesmo sintoma das v1.2.12/v1.2.13: sem
# herói identificado, o pipeline usava a role manual (Roles.txt) e o ranking saía
# na role errada — com o Roles.txt em SUP, opções de Suporte para quem estava de
# Mei (DPS). A correção é um segundo pré-processo (contraste LOCAL via CLAHE +
# Otsu), tentado só quando o padrão não devolve nome — ver player_hero._OCR_RECIPES.


def test_mei_detectada_na_fixture_2k():
    """detect() ponta a ponta na captura que motivou a correção."""
    with Image.open(FIXTURES_DIR / "2k" / "full2.jpg") as img:
        img.load()
    hero = player_hero.detect(img.convert("RGB"))
    assert hero is not None, "herói do jogador não identificado em 2k/full2.jpg"
    assert hero.key == normalize_hero_name("Mei")
    assert hero.role == "DPS"


def test_preprocesso_padrao_sozinho_nao_le_o_nome_da_fixture_2k():
    """Documenta a causa-raiz: com APENAS o recipe padrão o nome sai vazio.

    Se um dia o pré-processo padrão passar a ler esse recorte, este teste falha e
    o recipe alternativo pode ser reavaliado — é o gatilho para revisitar, não um
    comportamento desejado.
    """
    from owpick.infra import map_detect

    with Image.open(FIXTURES_DIR / "2k" / "full2.jpg") as img:
        img.load()
    full = img.convert("RGB")
    texto = map_detect.extract_text_from_image(full, player_hero.name_region(*full.size))
    assert player_hero.identify_hero(texto)[1] < player_hero.MIN_CONFIDENCE


def test_contraste_local_le_o_nome_curto():
    """O recipe alternativo lê "MEI" no recorte em que o padrão falha."""
    with Image.open(FIXTURES_DIR / "2k" / "full2.jpg") as img:
        img.load()
    full = img.convert("RGB")
    nome, score = player_hero.read_hero_name(full)
    assert nome == "Mei"
    assert score >= player_hero.MIN_CONFIDENCE_FALLBACK


def test_recipes_comecam_pelo_preprocesso_calibrado():
    """O primeiro recipe é o de sempre (mesmo pré-processo e mesmo limiar).

    Garante que a cascata é ADITIVA: nenhuma captura que já era lida corretamente
    passa a depender de um pré-processo alternativo, e o custo no caminho feliz
    continua sendo uma única chamada ao OCR.
    """
    recipe, preprocess, psm, threshold = player_hero._OCR_RECIPES[0]
    assert preprocess is None  # None => map_detect.preprocess_for_ocr
    assert psm == ocr_backends.DEFAULT_PSM
    assert threshold == player_hero.MIN_CONFIDENCE
    assert recipe == "padrao"
    # Os alternativos são mais exigentes: só sobrescrevem a role manual com uma
    # leitura limpa (ver MIN_CONFIDENCE_FALLBACK).
    assert all(r[3] == player_hero.MIN_CONFIDENCE_FALLBACK for r in player_hero._OCR_RECIPES[1:])


def test_contraste_local_produz_texto_preto_sobre_branco():
    """A binarização entrega o formato em que o Tesseract foi treinado."""
    ruidoso = Image.new("RGB", (60, 20), (10, 10, 12))
    ImageDraw.Draw(ruidoso).rectangle((10, 5, 30, 14), fill=(230, 230, 235))
    binario = player_hero._local_contrast_binary(ruidoso)

    cores = {tom for tom, qtd in enumerate(binario.convert("L").histogram()) if qtd}
    assert cores <= {0, 255}, f"binarização deixou tons intermediários: {sorted(cores)[:5]}"
    # Fundo branco (a margem/quiet zone) e traço preto: maioria branca.
    assert binario.convert("L").getpixel((0, 0)) == 255
    assert 0 in cores


def test_pontuacao_nao_penaliza_nenhum_nome_canonico():
    """Causa-raiz nº 1, generalizada: com o OCR lendo o nome LIMPO (maiúsculas,
    sem acento nem pontuação — tudo que o Tesseract consegue emitir), TODOS os
    heróis marcam 100. Antes o ponto/dois-pontos custavam pontos em nomes CURTOS
    ("D.Va" 85.7, "Soldier: 76" 95.2), corroendo a folga até o limiar."""
    for hero in get_all_heroes():
        ocr = player_hero._strip_upper(hero)  # o nome como o OCR o entrega
        name, score = player_hero.identify_hero(ocr)
        assert name == hero, f"{hero!r} lido {ocr!r} casou com {name!r}"
        assert score == 100.0, f"{hero!r} lido {ocr!r} marcou {score:.1f}, não 100"


# Ruído do badge observado nas capturas reais, como TOKEN separado.
BADGE_TOKENS = ["", " &", " @", " @&", " esi", " ies", " ses", " G&S", " S&S", " BS"]


def test_badge_como_token_separado_nao_derruba_nenhum_heroi():
    """Causa-raiz nº 2, generalizada: o token do badge é descartado, então nenhum
    herói perde pontos por causa dele — todos seguem acima do limiar."""
    for hero in get_all_heroes():
        limpo = player_hero._strip_upper(hero)
        for badge in BADGE_TOKENS:
            name, score = player_hero.identify_hero(limpo + badge)
            assert name == hero, f"{hero!r} + badge {badge!r} casou com {name!r}"
            assert score >= player_hero.MIN_CONFIDENCE, (
                f"{hero!r} + badge {badge!r} marcou {score:.1f}"
            )


def test_tokens_simbolicos_sao_descartados():
    """_strip_upper remove tokens sem alfanumérico e preserva os do nome."""
    assert player_hero._strip_upper("OVA &") == "OVA"
    assert player_hero._strip_upper("D.VA @&") == "DVA"
    assert player_hero._strip_upper("WRECKING BALL &") == "WRECKING BALL"
    assert player_hero._strip_upper("SOLDIER: 76 @") == "SOLDIER 76"


def test_ocr_so_com_badge_nao_casa_com_ninguem():
    """Se o OCR pegou só o badge, não há nome: rejeita (cai no fallback manual)."""
    for lixo in ("&", "@", "@&", "|", "  "):
        assert player_hero.identify_hero(lixo) == ("", 0.0), lixo


def test_detect_sem_nome_legivel_retorna_none():
    # Imagem sólida (sem texto) -> OCR vazio/lixo -> nenhuma role forçada.
    blank = Image.new("RGB", (1280, 720), (20, 20, 20))
    assert player_hero.detect(blank) is None


# ---------------------------------------------------------------------------
# Integração no pipeline: role detectada tem prioridade; fallback manual
# ---------------------------------------------------------------------------
def _setup_user(tmp_path, monkeypatch, role_manual: str, dps_heroes: list[str]):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    from owpick import paths

    paths.ensure_dirs()
    storage.write_role(role_manual)
    # Favoritos por role: só DPS.txt é lido quando a role detectada for DPS.
    with open(paths.user_file("DPS.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(dps_heroes))


def test_pipeline_usa_role_detectada_no_lugar_da_manual(tmp_path, monkeypatch):
    """Role manual = TANK, mas o jogador está de Sierra (DPS) na captura 720p:
    o ranking deve sair para DPS, usando os favoritos de DPS."""
    _setup_user(tmp_path, monkeypatch, "TANK", ["Tracer", "Genji", "Ashe"])
    img = _load_full("720p")
    monkeypatch.setattr(capture, "mss", _FakeMss(img))

    result = pipeline.run_pipeline()
    assert result is not None
    assert result.role == "DPS"  # role AUTO-detectada (Sierra), não a manual (TANK)
    assert set(result.playable) == {"Tracer", "Genji", "Ashe"}


def test_pipeline_cai_para_role_manual_quando_nao_detecta(tmp_path, monkeypatch):
    """Sem herói legível na captura, o pipeline mantém a role manual (fallback)."""
    _setup_user(tmp_path, monkeypatch, "DPS", ["Tracer", "Genji"])
    blank = Image.new("RGB", (1280, 720), (20, 20, 20))
    monkeypatch.setattr(capture, "mss", _FakeMss(blank))
    monkeypatch.setattr(player_hero, "detect", lambda _img: None)  # força o fallback

    result = pipeline.run_pipeline()
    assert result is not None
    assert result.role == "DPS"  # veio de Roles.txt (fallback)
