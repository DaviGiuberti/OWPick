"""settings.py — Settings único, tipado e validado do OWPick (tarefa 6.1).

Um único arquivo `settings.json` em %APPDATA%\\OWPick guarda as PREFERÊNCIAS do
usuário (hotkey, idioma, modo debug, overrides avançados). Ele é distinto dos
DADOS da aplicação (layouts/matrizes/templates, que vivem no bundle) e dos
DADOS do usuário gerados pelos menus (Roles.txt/favoritos, em infra.storage).

Princípios:
  - Dataclass + validação manual (sem pydantic — nenhuma dependência nova).
    Cada campo inválido gera uma mensagem clara e cai para o default; um campo
    quebrado nunca derruba o app nem invalida o resto do arquivo.
  - Campos avançados de calibração (limiar de ban/lineup, confiança do mapa,
    URL do updater) são OVERRIDES opcionais: `None` significa "use o default
    calibrado do módulo dono" (matching/map_detect/updater). Assim o valor
    canônico continua tendo UMA única fonte, junto da documentação de
    calibração, e o settings só o substitui quando o usuário pede.
  - `version` no arquivo permite upgrades de esquema no futuro.

Uso:
    from owpick import settings
    cfg = settings.get()        # cacheado; lê o arquivo uma vez por sessão
    settings.save(cfg)          # persiste (grava apenas campos conhecidos)
    settings.reload()           # invalida o cache (após save/edição externa)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from owpick import paths
from owpick.log import get_logger

log = get_logger("settings")

SETTINGS_FILENAME = "settings.json"
SETTINGS_VERSION = 1

# Idiomas com strings de UI/aliases suportados (tarefas 6.6 e 4.6).
VALID_LANGUAGES = ("pt-BR", "en")

# Hotkey padrão de captura (nomes de tecla da lib `keyboard`, minúsculos).
DEFAULT_HOTKEY = ("tab", "1")


@dataclass
class Profile:
    """Um perfil nomeado (tarefa 6.8): role + favoritos + preset de pesos +
    tier de stats. Ao ATIVAR um perfil, esses valores são aplicados aos
    mecanismos existentes (Roles.txt, arquivos de favoritos, settings)."""

    role: str | None = None  # "ALL"/"DPS"/"SUP"/"TANK"; None = não altera
    favorites: list[str] = field(default_factory=list)
    weights_preset: str = "equilibrado"
    scraper_tier: str = "GRANDMASTER_AND_CHAMPION"


@dataclass
class Settings:
    """Preferências do usuário. Defaults = comportamento atual do app."""

    version: int = SETTINGS_VERSION
    # Combinação de teclas da captura (tarefa 6.2). Nomes da lib `keyboard`.
    hotkey: list[str] = field(default_factory=lambda: list(DEFAULT_HOTKEY))
    # Idioma da UI e dos aliases de mapa ("pt-BR" | "en").
    language: str = "pt-BR"
    # Modo debug persistente (equivale à flag --debug).
    debug: bool = False
    # Exibir o "por quê" de cada recomendação do top do ranking (tarefa 6.4).
    explain_ranking: bool = False
    # Preset de pesos do modelo (tarefa 6.3): "equilibrado" (= atual),
    # "counter-first", "meta-first", "conforto+" (ver core.scoring.PRESETS).
    weights_preset: str = "equilibrado"
    # Modo avançado: overrides individuais dos pesos por cima do preset
    # (ex.: {"beta_syn": 1.2}). Campos válidos: alpha, lam, mu, beta_meta,
    # beta_ctr, beta_syn.
    custom_weights: dict[str, float] = field(default_factory=dict)
    # --- Overrides avançados (None = default calibrado do módulo dono) ---
    lineup_match_max_score: float | None = None  # canônico: infra.matching
    ban_match_max_score: float | None = None  # canônico: infra.matching
    map_min_confidence: float | None = None  # canônico: infra.map_detect
    updater_url: str | None = None  # canônico: infra.updater
    # Região/tier do scraper de stats (tarefa 5.3 / tools/coletar_stats.py).
    scraper_region: str = "AMER"
    scraper_tier: str = "GRANDMASTER_AND_CHAMPION"
    # Múltiplos perfis (tarefa 6.8): {nome: Profile}; active_profile = último
    # perfil aplicado (informativo — os valores efetivos vivem em Roles.txt/
    # favoritos/settings, gravados no momento da troca).
    profiles: dict[str, Profile] = field(default_factory=dict)
    active_profile: str | None = None


def settings_path() -> str:
    """Caminho absoluto do settings.json (dado do usuário)."""
    return paths.user_file(SETTINGS_FILENAME)


# ---------------------------------------------------------------------------
# Validação — cada campo inválido cai para o default com aviso claro
# ---------------------------------------------------------------------------
def _validate_field(name: str, value: object, default: object) -> tuple[object, str | None]:
    """Devolve (valor_validado, problema|None). Problema => usar default."""
    if name == "version":
        if isinstance(value, int) and value >= 1:
            return value, None
        return default, f"'version' deve ser um inteiro >= 1 (recebi {value!r})"

    if name == "hotkey":
        if (
            isinstance(value, list)
            and value
            and all(isinstance(k, str) and k.strip() for k in value)
        ):
            return [k.strip().lower() for k in value], None
        return default, f"'hotkey' deve ser uma lista de teclas não vazia (recebi {value!r})"

    if name == "language":
        if isinstance(value, str) and value in VALID_LANGUAGES:
            return value, None
        return default, f"'language' deve ser um de {list(VALID_LANGUAGES)} (recebi {value!r})"

    if name in ("debug", "explain_ranking"):
        if isinstance(value, bool):
            return value, None
        return default, f"'{name}' deve ser true/false (recebi {value!r})"

    if name == "weights_preset":
        # Import tardio para manter o settings leve no import (scoring puxa
        # numpy/pandas); os presets vivem no core (fonte única).
        from owpick.core.scoring import PRESETS

        if isinstance(value, str) and value in PRESETS:
            return value, None
        return default, f"'weights_preset' deve ser um de {sorted(PRESETS)} (recebi {value!r})"

    if name == "custom_weights":
        from owpick.core.scoring import WEIGHT_FIELD_NAMES

        if isinstance(value, dict) and all(
            k in WEIGHT_FIELD_NAMES and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in value.items()
        ):
            return {k: float(v) for k, v in value.items()}, None
        return default, (
            f"'custom_weights' deve mapear campos {list(WEIGHT_FIELD_NAMES)} "
            f"para números (recebi {value!r})"
        )

    if name in ("lineup_match_max_score", "ban_match_max_score", "map_min_confidence"):
        if value is None:
            return None, None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value), None
        return default, f"'{name}' deve ser um número > 0 ou null (recebi {value!r})"

    if name == "updater_url":
        if value is None:
            return None, None
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value, None
        return default, f"'updater_url' deve ser uma URL http(s) ou null (recebi {value!r})"

    if name == "active_profile":
        if value is None or (isinstance(value, str) and value.strip()):
            return value, None
        return default, f"'active_profile' deve ser um nome de perfil ou null (recebi {value!r})"

    if name == "profiles":
        if not isinstance(value, dict):
            return default, f"'profiles' deve ser um objeto {{nome: perfil}} (recebi {value!r})"
        profiles, problem = _parse_profiles(value)
        return profiles, problem

    if name in ("scraper_region", "scraper_tier"):
        if isinstance(value, str) and value.strip():
            return value.strip(), None
        return default, f"'{name}' deve ser um texto não vazio (recebi {value!r})"

    return value, None


def _parse_profiles(value: dict) -> tuple[dict[str, Profile], str | None]:
    """Valida {nome: perfil}. Perfis com campos inválidos são descartados com
    aviso; os válidos permanecem (um perfil quebrado não invalida os demais)."""
    from owpick.core.heroes import VALID_ROLES
    from owpick.core.scoring import PRESETS

    profiles: dict[str, Profile] = {}
    bad: list[str] = []
    for name, raw in value.items():
        if not (isinstance(name, str) and name.strip() and isinstance(raw, dict)):
            bad.append(str(name))
            continue
        role = raw.get("role")
        favorites = raw.get("favorites", [])
        preset = raw.get("weights_preset", "equilibrado")
        tier = raw.get("scraper_tier", "GRANDMASTER_AND_CHAMPION")
        valid = (
            (role is None or role in VALID_ROLES)
            and isinstance(favorites, list)
            and all(isinstance(h, str) for h in favorites)
            and isinstance(preset, str)
            and preset in PRESETS
            and isinstance(tier, str)
            and tier.strip()
        )
        if not valid:
            bad.append(name)
            continue
        profiles[name.strip()] = Profile(
            role=role, favorites=list(favorites), weights_preset=preset, scraper_tier=tier.strip()
        )
    if bad:
        return profiles, f"perfis inválidos descartados: {', '.join(bad)}"
    return profiles, None


def parse(data: dict) -> tuple[Settings, list[str]]:
    """
    Constrói um Settings validado a partir do dict do JSON. Retorna também a
    lista de problemas encontrados (campos inválidos caem para o default;
    chaves desconhecidas são ignoradas com aviso).
    """
    problems: list[str] = []
    result = Settings()
    known = {f.name for f in fields(Settings)}

    for key in data:
        if key not in known:
            problems.append(f"chave desconhecida ignorada: '{key}'")

    for f in fields(Settings):
        if f.name not in data:
            continue  # ausente -> default (permite arquivos parciais/antigos)
        default = getattr(result, f.name)
        value, problem = _validate_field(f.name, data[f.name], default)
        if problem:
            problems.append(f"{problem} — usando o padrão ({default!r})")
        setattr(result, f.name, value)

    result.version = SETTINGS_VERSION  # esquema corrente após o parse
    return result, problems


def load(path: str | None = None) -> tuple[Settings, list[str]]:
    """
    Lê e valida o settings.json. Ausente => defaults (primeira execução).
    JSON corrompido => defaults + problema reportado (nunca derruba o app).
    """
    if path is None:
        path = settings_path()
    if not os.path.exists(path):
        return Settings(), []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        # Degradação segura: settings ilegível não pode impedir o boot; o
        # usuário continua com os defaults e o problema fica registrado.
        log.warning("settings.json ilegível (%s); usando defaults", e)
        return Settings(), [f"settings.json ilegível ({e}) — usando os padrões"]
    if not isinstance(data, dict):
        return Settings(), ["settings.json não contém um objeto JSON — usando os padrões"]
    return parse(data)


def save(cfg: Settings, path: str | None = None) -> None:
    """Persiste o settings (apenas campos conhecidos, JSON indentado)."""
    if path is None:
        path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(cfg), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    reload()


# ---------------------------------------------------------------------------
# Acesso cacheado (uma leitura por sessão; reload() invalida)
# ---------------------------------------------------------------------------
_cached: Settings | None = None


def get() -> Settings:
    """Settings da sessão (cacheado). Problemas de validação vão para o log."""
    global _cached
    if _cached is None:
        _cached, problems = load()
        for p in problems:
            log.warning("settings: %s", p)
            print(f"[settings] AVISO: {p}")
    return _cached


def reload() -> None:
    """Invalida o cache (próximo get() relê o arquivo)."""
    global _cached
    _cached = None
