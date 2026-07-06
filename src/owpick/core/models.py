"""models.py — Tipos de domínio do OWPick (dataclasses).

A normalização de nomes acontece UMA vez, na fronteira, ao construir os
objetos (Hero.from_name). A partir daí o resto do código trabalha com tipos —
erros de semântica (trocar aliados por inimigos) viram erros de tipo/campo em
vez de bugs silenciosos de lista.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from owpick.core import heroes

if TYPE_CHECKING:
    from PIL.Image import Image

UNKNOWN_MAP = "UNKNOWN"


@dataclass(frozen=True)
class Hero:
    """Um herói identificado. `key` é a chave normalizada (lookup em matrizes)."""

    name: str
    role: str | None
    key: str

    @classmethod
    def from_name(cls, name: str) -> Hero:
        """Fronteira canônica: normaliza e resolve a role UMA única vez."""
        return cls(
            name=name,
            role=heroes.get_hero_role(name),
            key=heroes.normalize_hero_name(name),
        )


@dataclass(frozen=True)
class MatchResult:
    """Melhor match de UM slot: herói (ou None), score (MAE; menor = melhor)."""

    hero: Hero | None
    score: float
    confident: bool = True  # preparado p/ limiar de confiança do lineup (tarefa 4.1)


@dataclass
class Lineup:
    """Times identificados na captura (aliados SEM o próprio jogador)."""

    allies: list[Hero] = field(default_factory=list)
    enemies: list[Hero] = field(default_factory=list)

    def ally_keys(self) -> set[str]:
        return {h.key for h in self.allies}

    def ally_names(self) -> list[str]:
        return [h.name for h in self.allies]

    def enemy_names(self) -> list[str]:
        return [h.name for h in self.enemies]


@dataclass
class BanList:
    """Heróis banidos no competitivo (vazia em modos sem ban)."""

    heroes: list[Hero] = field(default_factory=list)

    def keys(self) -> set[str]:
        return {h.key for h in self.heroes}

    def names(self) -> list[str]:
        return [h.name for h in self.heroes]

    def __bool__(self) -> bool:
        return bool(self.heroes)


@dataclass(frozen=True)
class MapDetection:
    """Mapa identificado via OCR; UNKNOWN degrada o MetaStrength para 0."""

    name: str = UNKNOWN_MAP
    score: float = 0.0

    @property
    def known(self) -> bool:
        return self.name != UNKNOWN_MAP


@dataclass
class CaptureResult:
    """
    Recortes EM MEMÓRIA de uma captura (o disco deixou de ser o barramento de
    dados do pipeline — PNGs são gravados apenas como artefato de debug).

    portraits: {variação_de_perk: {nome_do_slot(ex.: "ally1.png"): recorte}}
    bans:      {"ban1.png"..: recorte exato do slot de ban}
    """

    full: Image
    resolution: tuple[int, int]
    portraits: dict[str, dict[str, Image]] = field(default_factory=dict)
    bans: dict[str, Image] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return self.resolution[0]

    @property
    def height(self) -> int:
        return self.resolution[1]


@dataclass
class Recommendation:
    """Linha do ranking final. `reasons` alimenta a explicabilidade (tarefa 6.4)."""

    hero: Hero
    meta: float
    counter: float
    synergy: float
    total: float
    reasons: list[str] = field(default_factory=list)
