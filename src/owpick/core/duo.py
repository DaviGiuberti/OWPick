"""duo.py — Regra de dupla de DPS por tank inimigo (coluna DUO). Puro, zero I/O.

Substitui a antiga sinergia DPS × DPS por categoria (v1.2.12–v1.2.16): em vez de
dois DPS se (anti-)sinergizarem entre si, a DUPLA de DPS do meu time ganha ou
perde prioridade conforme o TANK INIMIGO. Classes, regras e valores vêm de
`data/dps_duo_rules.json` (lido pela infra e passado por parâmetro):

  - dois eixos de classes, cada um cobrindo os 23 DPS: "dano" (Forte/Médio) e
    "estilo" (Hitscan/Flex/Os dois); "flanker" é registrada, sem efeito;
  - cada tank pertence a uma REGRA: o valor de cada dupla de classes de um eixo
    (par sem ordem; par ausente = 0);
  - TRIOS: uma dupla (num eixo) + um suporte aliado, contra uma lista de tanks.

Dois usos, com condições próprias:

  - ranking (`duo_terms`): jogando de DPS, a dupla é o candidato + o ÚNICO DPS
    aliado, contra o ÚNICO tank inimigo; o trio vai para quem o completa (o DPS
    candidato com o suporte aliado, ou o suporte candidato jogando de SUP);
  - Enemy Threat (`duo_threat_value`): jogando de SUP/TANK, a dupla de DPS
    aliada JÁ formada (exatamente 2 DPS) muda a ameaça do único tank inimigo.

Fora disso (Fila Aberta, 0 ou 2+ DPS aliados no ranking, 0 ou 2+ tanks
inimigos) a regra vale 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from owpick.core import heroes
from owpick.core.heroes import normalize_hero_name

PAIR_SEPARATOR = "+"  # "Forte+Médio" no JSON

ClassPair = tuple[str, str]


def class_pair(class_a: str, class_b: str) -> ClassPair:
    """Par de classes SEM ordem: class_pair("Médio", "Forte") == ("Forte", "Médio")."""
    return (class_a, class_b) if class_a <= class_b else (class_b, class_a)


def parse_class_pair(text: str) -> ClassPair:
    """'Hitscan+Os dois' -> par sem ordem. Exige exatamente duas classes."""
    parts = [p.strip() for p in text.split(PAIR_SEPARATOR)]
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"par de classes inválido: {text!r}")
    return class_pair(parts[0], parts[1])


@dataclass(frozen=True)
class TankRule:
    """Valor de cada dupla de classes de um eixo contra um grupo de tanks."""

    name: str
    axis: str
    pairs: dict[ClassPair, float]
    tanks: frozenset[str]  # chaves normalizadas


@dataclass(frozen=True)
class Trio:
    """Dupla de DPS (num eixo) + um suporte aliado, contra um grupo de tanks."""

    support: str  # nome como no JSON (vai para a explicação)
    support_key: str
    axis: str
    pair: ClassPair
    value: float
    tanks: frozenset[str]  # chaves normalizadas


@dataclass(frozen=True)
class DuoRules:
    """Regras de dupla prontas para o scoring (chaves de herói normalizadas)."""

    classes: dict[str, dict[str, str]]  # eixo -> {chave do herói: classe}
    flanker: frozenset[str]
    rules: tuple[TankRule, ...]
    trios: tuple[Trio, ...]

    def class_of(self, axis: str, hero_key: str) -> str | None:
        return self.classes.get(axis, {}).get(hero_key)

    def pair_of(self, axis: str, key_a: str, key_b: str) -> ClassPair | None:
        """Par de classes de dois heróis no eixo (None se algum não tem classe)."""
        cls_a, cls_b = self.class_of(axis, key_a), self.class_of(axis, key_b)
        if cls_a is None or cls_b is None:
            return None
        return class_pair(cls_a, cls_b)

    def rule_for(self, tank_key: str) -> TankRule | None:
        return next((r for r in self.rules if tank_key in r.tanks), None)


# Sem regras: tudo neutro.
EMPTY_DUO_RULES = DuoRules(classes={}, flanker=frozenset(), rules=(), trios=())


def parse_duo_rules(data: dict) -> DuoRules:
    """Converte o JSON de `data/dps_duo_rules.json` em `DuoRules`.

    Só normaliza e estrutura: a CONSISTÊNCIA (cobertura dos 23 DPS, tank com
    exatamente uma regra, classes conhecidas...) é conferida por
    `infra.validation.validate_duo_rules`. Estrutura quebrada (chave ausente, par
    mal escrito, valor não numérico) levanta KeyError/ValueError/TypeError.
    """
    classes = {
        str(axis): {
            normalize_hero_name(hero): str(cls) for cls, names in by_class.items() for hero in names
        }
        for axis, by_class in data["axes"].items()
    }
    rules = tuple(
        TankRule(
            name=str(r["name"]),
            axis=str(r["axis"]),
            pairs={parse_class_pair(p): float(v) for p, v in r["pairs"].items()},
            tanks=frozenset(normalize_hero_name(t) for t in r["tanks"]),
        )
        for r in data["rules"]
    )
    trios = tuple(
        Trio(
            support=str(t["support"]),
            support_key=normalize_hero_name(t["support"]),
            axis=str(t["axis"]),
            pair=parse_class_pair(t["pair"]),
            value=float(t["value"]),
            tanks=frozenset(normalize_hero_name(x) for x in t["tanks"]),
        )
        for t in data.get("trios", [])
    )
    return DuoRules(
        classes=classes,
        flanker=frozenset(normalize_hero_name(h) for h in data.get("flanker", [])),
        rules=rules,
        trios=trios,
    )


# ---------------------------------------------------------------------------
# Avaliação
# ---------------------------------------------------------------------------
@cache
def _role(name: str) -> str | None:
    # get_hero_role varre os 54 heróis a cada chamada; aqui ele roda para cada
    # aliado/inimigo de cada candidato, então o resultado fica em cache.
    return heroes.get_hero_role(name)


def _with_role(names: list[str], role: str) -> list[tuple[str, str]]:
    """(nome, chave) dos heróis da lista que são da `role` (ignora slots vazios)."""
    return [(n, normalize_hero_name(n)) for n in names if n and _role(n) == role]


def _single_tank(enemies: list[str]) -> tuple[str, str] | None:
    """(nome, chave) do ÚNICO tank inimigo; None com 0 ou 2+ tanks."""
    tanks = _with_role(enemies, "TANK")
    return tanks[0] if len(tanks) == 1 else None


def _pair_value(
    rules: DuoRules, tank_key: str, key_a: str, key_b: str
) -> tuple[float, str, str] | None:
    """(valor, classe de a, classe de b) da dupla na regra do tank; None sem regra/classe."""
    rule = rules.rule_for(tank_key)
    if rule is None:
        return None
    cls_a, cls_b = rules.class_of(rule.axis, key_a), rules.class_of(rule.axis, key_b)
    if cls_a is None or cls_b is None:
        return None
    return rule.pairs.get(class_pair(cls_a, cls_b), 0.0), cls_a, cls_b


def _matching_trios(rules: DuoRules, tank_key: str, key_a: str, key_b: str) -> list[Trio]:
    """Trios que valem contra o tank e cuja dupla (no eixo do trio) é a de a + b."""
    return [
        t
        for t in rules.trios
        if tank_key in t.tanks and rules.pair_of(t.axis, key_a, key_b) == t.pair
    ]


def duo_terms(
    candidate: str,
    allies: list[str],
    enemies: list[str],
    role: str | None,
    rules: DuoRules,
) -> list[tuple[float, str]]:
    """Termos da coluna DUO de um candidato: [(valor, rótulo da razão)], só os ≠ 0.

    Jogando de DPS — candidato DPS, exatamente 1 DPS aliado `d` e exatamente 1
    tank inimigo `t`:
      - dupla: valor do par (classe do candidato, classe de `d`) na regra de `t`;
      - trio: valor de cada trio cuja dupla é a do candidato + `d`, cujo suporte
        é aliado e cuja lista contém `t`.
    Jogando de SUP — candidato = suporte de um trio, exatamente 2 DPS aliados e
    exatamente 1 tank inimigo: o trio, se a dupla aliada bate.
    Qualquer outra role (TANK, ALL, None) ou formato de time ⇒ lista vazia.

    Os valores saem CRUS (sem β_duo) e o rótulo vem sem o número: o scoring
    formata a razão com a contribuição já ponderada, como nas outras colunas.
    """
    if role not in ("DPS", "SUP"):
        return []
    tank = _single_tank(enemies)
    if tank is None:
        return []
    tank_name, tank_key = tank
    cand_key = normalize_hero_name(candidate)
    ally_dps = _with_role(allies, "DPS")
    terms: list[tuple[float, str]] = []

    if role == "DPS":
        if _role(cand_key) != "DPS" or len(ally_dps) != 1:
            return []
        ally_name, ally_key = ally_dps[0]
        ally_keys = {normalize_hero_name(a) for a in allies if a}
        duo = _pair_value(rules, tank_key, cand_key, ally_key)
        if duo is not None and duo[0]:
            value, cls_cand, cls_ally = duo
            terms.append((value, f"dupla {cls_cand}+{cls_ally} com {ally_name} contra {tank_name}"))
        for trio in _matching_trios(rules, tank_key, cand_key, ally_key):
            if trio.support_key in ally_keys and trio.value:
                terms.append((trio.value, f"trio com {trio.support} contra {tank_name}"))
        return terms

    # role == "SUP": a dupla aliada já está formada; o suporte candidato fecha o trio.
    if len(ally_dps) != 2:
        return []
    (name_1, key_1), (name_2, key_2) = ally_dps
    for trio in _matching_trios(rules, tank_key, key_1, key_2):
        if trio.support_key == cand_key and trio.value:
            terms.append((trio.value, f"trio com {name_1} e {name_2} contra {tank_name}"))
    return terms


def duo_threat_value(
    enemy: str,
    allies: list[str],
    enemies: list[str],
    role: str | None,
    rules: DuoRules,
) -> float:
    """Valor da dupla de DPS ALIADA já formada contra o tank inimigo `enemy`.

    Só jogando de SUP ou TANK, com exatamente 2 DPS aliados e `enemy` sendo o
    ÚNICO tank inimigo: valor do par dos 2 DPS na regra do tank, mais o de cada
    trio cuja dupla bate, cujo suporte é aliado e cuja lista contém o tank.
    Positivo = a dupla é boa para o meu time, então o tank fica MENOS ameaçador
    (o scoring soma −λ·valor ao raw dele). Fora das condições ⇒ 0.
    """
    if role not in ("SUP", "TANK"):
        return 0.0
    enemy_key = normalize_hero_name(enemy)
    tank = _single_tank(enemies)
    if tank is None or tank[1] != enemy_key:
        return 0.0
    ally_dps = _with_role(allies, "DPS")
    if len(ally_dps) != 2:
        return 0.0
    (_, key_1), (_, key_2) = ally_dps
    ally_keys = {normalize_hero_name(a) for a in allies if a}
    duo = _pair_value(rules, enemy_key, key_1, key_2)
    value = duo[0] if duo is not None else 0.0
    for trio in _matching_trios(rules, enemy_key, key_1, key_2):
        if trio.support_key in ally_keys:
            value += trio.value
    return value
