# -*- mode: python ; coding: utf-8 -*-
"""
overwatch.spec — Especificação do PyInstaller para o OWPick (one-folder).

Estrutura do repositório (o bundle ESPELHA os mesmos caminhos relativos, para
que utils.resource_path funcione idêntico em .py e .exe):

    src/owpick/       módulos Python (main.py = entry point)
    assets/heroes/    templates de imagem       -> bundle: assets/heroes/
    assets/ocr/       Tesseract OCR embutido    -> bundle: assets/ocr/
    data/             layouts/, stats, matrizes .csv -> bundle: data/
                      (os .xlsx de edição e tools/xlsx_to_csv.py NÃO entram)
    version.txt       versão (raiz)             -> bundle: raiz (_MEIPASS)

Este arquivo vive em packaging/; os caminhos abaixo são resolvidos a partir
da raiz do repositório (pai de packaging/), então o build funciona sendo
invocado de qualquer diretório (build.bat cuida disso).
"""

import os
import sys

# Raiz do repositório (o .spec vive em packaging/). SPECPATH é injetado pelo
# PyInstaller com o diretório deste arquivo.
BASE_DIR = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821
SRC_DIR = os.path.join(BASE_DIR, "src", "owpick")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
DATA_DIR = os.path.join(BASE_DIR, "data")

# ============================================================================
# VALIDAÇÃO DOS RECURSOS
# ============================================================================

OCR_PATH = os.path.join(ASSETS_DIR, "ocr")
if not os.path.exists(os.path.join(OCR_PATH, "tesseract.exe")):
    print("ERRO: assets/ocr/tesseract.exe não encontrado — Tesseract embutido é obrigatório.")
    sys.exit(1)
if not os.path.exists(os.path.join(OCR_PATH, "tessdata")):
    print("ERRO: assets/ocr/tessdata/ não encontrada.")
    sys.exit(1)
if not os.path.exists(os.path.join(ASSETS_DIR, "heroes")):
    print("ERRO: assets/heroes/ (templates) não encontrada.")
    sys.exit(1)

print("✓ Recursos validados (assets/ocr, assets/heroes, data/)")

# ============================================================================
# ANÁLISE
# ============================================================================

a = Analysis(
    # Entry = bootstrap do pacote owpick (owpick/__main__.py). pathex inclui a
    # RAIZ src/ para que `import owpick.*` resolva no bundle.
    [os.path.join(SRC_DIR, "__main__.py")],
    pathex=[os.path.join(BASE_DIR, "src")],
    binaries=[],
    datas=[
        # O destino espelha o caminho relativo usado por resource_path.
        (os.path.join(ASSETS_DIR, "heroes"), os.path.join("assets", "heroes")),
        (os.path.join(ASSETS_DIR, "ocr"), os.path.join("assets", "ocr")),
        # Strings de UI por idioma (tarefa 6.6).
        (os.path.join(ASSETS_DIR, "i18n"), os.path.join("assets", "i18n")),
        (os.path.join(DATA_DIR, "layouts", "ow_hero_select.json"), os.path.join("data", "layouts")),
        (os.path.join(DATA_DIR, "stats_inputs.csv"), "data"),
        # Matrizes em CSV (tarefa 5.1). O programa lê APENAS estes .csv; os .xlsx
        # de EDIÇÃO e o conversor tools/xlsx_to_csv.py NÃO são empacotados.
        (os.path.join(DATA_DIR, "synergies.csv"), "data"),
        (os.path.join(DATA_DIR, "counters.csv"), "data"),
        (os.path.join(BASE_DIR, "version.txt"), "."),
    ],
    hiddenimports=[
        # ===== BIBLIOTECAS PRINCIPAIS =====
        # pandas lê os .csv (matrizes + stats). openpyxl NÃO é mais runtime — os
        # .xlsx só são lidos pelo conversor offline tools/xlsx_to_csv.py (5.1).
        "pandas",
        "cv2",
        "numpy",
        "PIL",
        "PIL.Image",
        "PIL.ImageOps",
        "mss",
        "unidecode",
        "rapidfuzz",
        "rapidfuzz.process",
        "rapidfuzz.fuzz",
        "rapidfuzz.distance",
        "pytesseract",
        "keyboard",
        "rich",  # console rico da ui (tabela/painel/spinner — tarefa 6.5)
        # ===== PACOTE DO PROJETO (src/owpick) =====
        "owpick",
        "owpick.__main__",
        "owpick.log",
        "owpick.paths",
        "owpick.settings",
        "owpick.i18n",
        "owpick.pipeline",
        "owpick.core.heroes",
        "owpick.core.resolution",
        "owpick.core.models",
        "owpick.core.ports",
        "owpick.core.scoring",
        "owpick.infra.resources",
        "owpick.infra.datasource",
        "owpick.infra.ocr_backends",
        "owpick.infra.validation",
        "owpick.infra.stats_update",
        "owpick.infra.storage",
        "owpick.infra.capture",
        "owpick.infra.matching",
        "owpick.infra.map_detect",
        "owpick.infra.player_hero",
        "owpick.infra.perf",
        "owpick.infra.updater",
        "owpick.ui.console",
        "owpick.ui.roles",
        "owpick.ui.hotkey",
        "owpick.ui.sim",
        "owpick.ui.profiles",
        "owpick.ui.weights",
        "owpick.ui.favorites",
        "owpick.ui.ranking_view",
        # ===== DEPENDÊNCIAS DE C-EXTENSIONS =====
        "cv2.data",
        "PIL._imaging",
        "mss.windows",
        "pytesseract.pytesseract",
        "rapidfuzz.distance.Levenshtein",
        # ===== STDLIB USADA DINAMICAMENTE =====
        "msvcrt",
        "logging.handlers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "tkinter",
        "scipy",
        "IPython",
        "jupyter",
        "notebook",
        "tornado",
        "sphinx",
        "pytest",
        "setuptools",
        "_pytest",
        "pygments",
        "jinja2",
        "docutils",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ============================================================================
# COMPILAÇÃO
# ============================================================================

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OWPick",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # app de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS_DIR, "icone.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OWPick",
)
