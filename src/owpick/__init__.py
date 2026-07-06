"""OWPick — recomendação de heróis de Overwatch a partir de captura de tela.

Arquitetura em três camadas (ver DOCUMENTACAO.md):
    owpick.core   — modelo de domínio, dados de heróis/mapas, matemática de
                    resolução e scoring. ZERO I/O.
    owpick.infra  — captura de tela, template matching, OCR, updater e
                    persistência (arquivos, planilhas, config). Faz o I/O.
    owpick.ui     — console (menus, hotkeys, formatação). A única que imprime.

`owpick.pipeline` reúne os casos de uso (run_pipeline) que a UI consome.
"""
