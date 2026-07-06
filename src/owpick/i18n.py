"""i18n.py — Strings de UI centralizadas por idioma (tarefa 6.6, cross-cutting).

As mensagens visíveis ao usuário vivem em `assets/i18n/{idioma}.json` (JSON
simples, PT-BR e EN) e seguem o padrão "o que houve + o que fazer". O idioma
vem do settings.json (tarefa 6.1; default pt-BR).

Uso:
    from owpick.i18n import t
    print(t("pipeline.role_missing"))
    print(t("boot.hotkey_hint", hotkey="TAB+1"))

Regras de degradação (uma string nunca derruba o app):
  - idioma sem arquivo/chave -> cai para o pt-BR;
  - chave inexistente também no pt-BR -> devolve a própria chave;
  - placeholder faltando no format -> devolve o texto cru.

Nota de escopo: as RAZÕES do ranking (tarefa 6.4) são geradas no core (puro) e
permanecem em pt-BR — internacionalizá-las exigiria injetar i18n no core.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from owpick.infra.resources import resource_path
from owpick.log import get_logger

log = get_logger("i18n")

I18N_DIR = os.path.join("assets", "i18n")
DEFAULT_LANGUAGE = "pt-BR"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict[str, str]:
    """Tabela de strings do idioma (cacheada). {} se ausente/ilegível."""
    path = resource_path(os.path.join(I18N_DIR, f"{lang}.json"))
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        log.warning("tabela de strings '%s' ausente/ilegível", lang, exc_info=True)
        return {}


def t(key: str, **kwargs: object) -> str:
    """String da UI no idioma do settings (fallback pt-BR -> a própria chave)."""
    from owpick import settings  # tardio: evita ciclo no import do pacote

    lang = settings.get().language
    text = _load(lang).get(key)
    if text is None and lang != DEFAULT_LANGUAGE:
        text = _load(DEFAULT_LANGUAGE).get(key)
    if text is None:
        log.warning("chave de i18n desconhecida: %s", key)
        return key
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        log.warning("placeholders inválidos na chave %s", key)
        return text
