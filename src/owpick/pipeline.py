"""pipeline.py — Casos de uso do OWPick (camada de aplicação).

Reúne infra (captura/matching/OCR/dados) e core (scoring) num fluxo que a UI
consome. Não imprime o ranking (isso é da ui); usa um callback `report` opcional
para as mensagens de progresso, mantendo a apresentação fora daqui.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from owpick import settings
from owpick.core.heroes import normalize_hero_name
from owpick.core.models import BanList, Lineup, MapDetection, Recommendation
from owpick.core.scoring import (
    compute_threat_weights,
    load_meta_strength,
    rank_heroes,
    resolve_weights,
)
from owpick.i18n import t
from owpick.infra import capture as capture_mod
from owpick.infra import datasource, map_detect, matching, storage
from owpick.log import get_logger

log = get_logger("pipeline")

# Callback de progresso (UI passa `print`); None = silencioso.
Reporter = Callable[[str], None] | None


def _report(report: Reporter, msg: str) -> None:
    if report is not None:
        report(msg)


@dataclass
class RankingResult:
    """Resultado completo do ranking, pronto para a ui formatar."""

    role: str
    playable: list[str]
    allies: list[str]
    enemies: list[str]
    banned: list[str]
    mapa: str
    meta_available: bool
    threat_weights: dict[str, float]
    recommendations: list[Recommendation]
    excluded_ally: list[str] = field(default_factory=list)
    excluded_ban: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Análise da captura (TAB+1): captura -> matching -> OCR do mapa
# ---------------------------------------------------------------------------
def analyze(
    report: Reporter = None,
    save_debug: bool = False,
) -> tuple[Lineup, BanList, MapDetection]:
    """Captura a tela e devolve (lineup, bans, mapa) — tudo em memória."""
    _report(report, t("pipeline.capturing"))
    cap = capture_mod.capture()
    if save_debug:
        capture_mod.save_debug_artifacts(cap)

    def _match() -> tuple[Lineup, BanList, dict]:
        """Matching de bans + lineup (template matching, CPU/SIMD via OpenCV)."""
        try:
            bans = matching.match_bans(cap)
        except Exception:  # noqa: BLE001
            log.warning("falha ao processar bans", exc_info=True)
            bans = BanList()
        lineup, slots = matching.match_lineup(cap)
        return lineup, bans, slots

    def _detect_map() -> MapDetection:
        """OCR do mapa (Tesseract em subprocesso — libera o GIL na espera)."""
        try:
            return map_detect.detect(cap.full)
        except Exception:  # noqa: BLE001
            log.warning("falha ao identificar o mapa", exc_info=True)
            return MapDetection()

    # O OCR do mapa (subprocess-bound) roda em paralelo ao matching de
    # lineup+bans (OpenCV libera o GIL), tirando o OCR do caminho crítico.
    # Os resultados são reunidos antes do ranking.
    _report(report, t("pipeline.comparing"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        map_future = pool.submit(_detect_map)
        lineup, bans, slots = _match()
        detection = map_future.result()

    # Reporta slots do lineup NÃO identificados (score acima do limiar de
    # confiança) — a pior falha silenciosa era ranquear sobre lineup fictício.
    for slot_name in sorted(slots):
        mr = slots[slot_name]
        if not mr.confident:
            _report(
                report,
                t("pipeline.slot_unidentified", slot=slot_name[:-4], score=f"{mr.score:.2f}"),
            )

    return lineup, bans, detection


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def rank(
    role: str,
    playable: list[str],
    allies: list[str],
    enemies: list[str],
    banned: list[str],
    mapa: str,
) -> RankingResult:
    """Calcula o ranking a partir de dados já resolvidos (nomes)."""
    ally_matrix = datasource.get_ally_matrix()
    enemy_matrix = datasource.get_enemy_matrix()

    # Pesos efetivos do modelo: preset do settings.json + overrides do modo
    # avançado (tarefa 6.3). Default = "equilibrado" (modelo atual).
    cfg = settings.get()
    weights = resolve_weights(cfg.weights_preset, cfg.custom_weights)

    meta = load_meta_strength(datasource.read_stats_inputs(), mapa, alpha=weights.alpha)
    threat = compute_threat_weights(
        enemies, enemy_matrix, allies, meta, lam=weights.lam, mu=weights.mu
    )

    ally_keys = {normalize_hero_name(a) for a in allies if a}
    ban_keys = {normalize_hero_name(b) for b in banned if b}
    excluded_ally = [h for h in playable if normalize_hero_name(h) in ally_keys]
    excluded_ban = [
        h
        for h in playable
        if normalize_hero_name(h) in ban_keys and normalize_hero_name(h) not in ally_keys
    ]

    recs, _excluded = rank_heroes(
        playable,
        allies,
        enemies,
        ally_matrix,
        enemy_matrix,
        threat,
        meta,
        excluded_keys=ally_keys | ban_keys,
        weights=weights,
        mapa=mapa,
    )

    return RankingResult(
        role=role,
        playable=playable,
        allies=allies,
        enemies=enemies,
        banned=banned,
        mapa=mapa,
        meta_available=bool(meta),
        threat_weights=threat,
        recommendations=recs,
        excluded_ally=excluded_ally,
        excluded_ban=excluded_ban,
    )


def run_pipeline(report: Reporter = None, save_debug: bool = False) -> RankingResult | None:
    """
    Caso de uso completo do TAB+1: captura, identifica e ranqueia.
    Retorna None se pré-requisitos (role/favoritos) estiverem ausentes.
    """
    role = storage.read_role()
    if role is None:
        _report(report, t("pipeline.role_missing"))
        return None
    try:
        playable = storage.read_playable_heroes(role)
    except OSError:
        _report(report, t("pipeline.favorites_missing", role=role))
        return None

    lineup, bans, detection = analyze(report=report, save_debug=save_debug)
    return rank(
        role=role,
        playable=playable,
        allies=lineup.ally_names(),
        enemies=lineup.enemy_names(),
        banned=bans.names(),
        mapa=detection.name,
    )


def rank_from_files() -> RankingResult | None:
    """
    Fluxo standalone (equivalente ao antigo choose_ow_hero): lê role,
    favoritos, lineup.txt/bans.txt/current_map.txt do disco e ranqueia.
    """
    role = storage.read_role()
    if role is None:
        print("Arquivo 'Roles.txt' ausente ou inválido!")
        return None
    try:
        playable = storage.read_playable_heroes(role)
    except OSError:
        print(f"Arquivo '{role}.txt' não encontrado! Defina seus favoritos.")
        return None
    try:
        allies, enemies = storage.read_lineup()
    except FileNotFoundError:
        print("Arquivo 'lineup.txt' não encontrado. Rode a análise de imagem (TAB+1) primeiro.")
        return None
    banned = storage.read_bans()
    mapa = storage.read_current_map()
    return rank(role, playable, allies, enemies, banned, mapa)
