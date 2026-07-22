"""Testes da detecção automática do herói/role do jogador (v1.2.10).

Cobre o módulo infra/player_hero (OCR do nome + fuzzy match + role) sobre as
capturas reais em tests/fixtures/<res>/full.png, o fallback quando não há herói
legível, o escalonamento da região por resolução e a integração no pipeline
(role detectada tem prioridade sobre a role manual, com fallback ao Roles.txt).
"""

from pathlib import Path

from PIL import Image

from owpick import pipeline
from owpick.core.heroes import normalize_hero_name
from owpick.infra import capture, player_hero, storage

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESOLUTIONS = ["720p", "1080p", "2k"]

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
    with Image.open(FIXTURES_DIR / res / "full.png") as img:
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
