# -*- mode: python ; coding: utf-8 -*-
"""
Arquivo de especificação do PyInstaller para Overwatch Helper
Versão: TESSERACT OCR EMBUTIDO (OPÇÃO 2)
Autor: [Seu Nome]
Versão: 2.0

IMPORTANTE:
- Esta configuração INCLUI o Tesseract OCR completo no executável
- A pasta 'ocr' deve estar ao lado do main.py com o Tesseract completo
- O executável resultante será maior (~60-100 MB), mas totalmente portátil
- Usuários NÃO precisam instalar nada separadamente
"""

import os
import sys

block_cipher = None

# ============================================================================
# CONFIGURAÇÃO DOS CAMINHOS
# ============================================================================

# Caminho base do projeto
BASE_DIR = os.path.dirname(os.path.abspath('main.py'))

# Caminho da pasta OCR com o Tesseract completo
OCR_PATH = os.path.join(BASE_DIR, 'ocr')

# ============================================================================
# VALIDAÇÃO DA PASTA OCR
# ============================================================================

if not os.path.exists(OCR_PATH):
    print("=" * 70)
    print("ERRO: Pasta 'ocr' não encontrada!")
    print("=" * 70)
    print(f"Esperado em: {OCR_PATH}")
    print()
    print("A pasta 'ocr' deve conter o Tesseract OCR completo:")
    print("  ocr/")
    print("  ├── tesseract.exe")
    print("  └── tessdata/")
    print("      ├── eng.traineddata")
    print("      ├── por.traineddata")
    print("      └── [outros arquivos]")
    print()
    print("Por favor, copie a pasta completa do Tesseract para 'ocr'")
    print("=" * 70)
    sys.exit(1)

tesseract_exe = os.path.join(OCR_PATH, 'tesseract.exe')
if not os.path.exists(tesseract_exe):
    print("=" * 70)
    print("ERRO: tesseract.exe não encontrado em ocr/tesseract.exe!")
    print("=" * 70)
    sys.exit(1)

tessdata = os.path.join(OCR_PATH, 'tessdata')
if not os.path.exists(tessdata):
    print("=" * 70)
    print("ERRO: Pasta tessdata não encontrada em ocr/tessdata/!")
    print("=" * 70)
    sys.exit(1)

print("✓ Pasta 'ocr' encontrada e validada")
print(f"  Tesseract: {tesseract_exe}")
print(f"  Tessdata: {tessdata}")

# ============================================================================
# COLETA DE BINÁRIOS E DADOS
# ============================================================================

# Binários específicos (caso necessário)
tesseract_binaries = []

# Dados para incluir no executável
tesseract_datas = [
    # Inclui toda a pasta OCR (Tesseract completo)
    ('ocr', 'ocr'),
]

# ============================================================================
# ANÁLISE DO PYINSTALLER
# ============================================================================

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=tesseract_binaries,
    datas=[
        # ===== ARQUIVOS DO PROJETO =====
        # Inclui a pasta com templates de imagens dos heróis
        ('heroes', 'heroes'),
        
        # Inclui as planilhas de dados (sinergias e counters)
        ('heroes ally.xlsx', '.'),
        ('heroes enemy.xlsx', '.'),
        
        # ===== TESSERACT OCR COMPLETO =====
        # Inclui toda a pasta OCR com Tesseract
        ('ocr', 'ocr'),
        
        # Se você tiver ChromeDriver, descomente a linha abaixo:
        # ('chromedriver.exe', '.'),
    ],
    hiddenimports=[
        # ===== BIBLIOTECAS PRINCIPAIS =====
        'pandas',
        'openpyxl',
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
        'mss',
        'selenium',
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.options',
        'unidecode',
        'rapidfuzz',
        'rapidfuzz.process',
        'rapidfuzz.fuzz',
        'rapidfuzz.distance',
        'pytesseract',
        'keyboard',
        
        # ===== SEUS MÓDULOS PYTHON =====
        'choose_ow_hero',
        'comparar',
        'compararMapa',  # NOVO: Módulo de comparação de mapas via OCR
        'favoriteHero',
        'map',
        'retirarWinrate',
        'roles',
        'screenshot',
        'site_scrapper',
        
        # ===== DEPENDÊNCIAS DO PANDAS/OPENPYXL =====
        'openpyxl.cell',
        'openpyxl.cell._writer',
        'openpyxl.styles',
        'openpyxl.styles.fonts',
        'openpyxl.styles.fills',
        'openpyxl.styles.colors',
        'openpyxl.worksheet',
        'openpyxl.worksheet.worksheet',
        'et_xmlfile',
        
        # ===== DEPENDÊNCIAS DO OPENCV =====
        'cv2.data',
        'numpy.core',
        'numpy.core._multiarray_umath',
        
        # ===== DEPENDÊNCIAS DO PIL =====
        'PIL._imaging',
        'PIL.ImageOps',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        
        # ===== DEPENDÊNCIAS DO MSS =====
        'mss.windows',
        'mss.linux',
        'mss.darwin',
        
        # ===== DEPENDÊNCIAS DO SELENIUM =====
        'selenium.webdriver.common',
        'selenium.webdriver.common.by',
        'selenium.webdriver.common.keys',
        'selenium.webdriver.support',
        'selenium.webdriver.support.ui',
        'selenium.webdriver.support.expected_conditions',
        
        # ===== DEPENDÊNCIAS DO PYTESSERACT =====
        'pytesseract.pytesseract',
        
        # ===== DEPENDÊNCIAS DO RAPIDFUZZ =====
        'rapidfuzz.distance.Levenshtein',
        
        # ===== DEPENDÊNCIAS DO UNIDECODE =====
        'unidecode',
        
        # ===== MÓDULOS PADRÃO DO PYTHON =====
        'unicodedata',
        'difflib',
        'pathlib',
        'json',
        'html',
        're',
        'time',
        'threading',
        'math',
        'os',
        'sys',
        'subprocess',
        'shutil',
        'tempfile',
        'logging',
        'datetime',
        'collections',
        'itertools',
        'functools',
        'io',
        'base64',
        'urllib',
        'urllib.parse',
        'urllib.request',
        'msvcrt',
        
        # ===== DEPENDÊNCIAS ADICIONAIS =====
        'pkg_resources',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclui bibliotecas desnecessárias para reduzir tamanho
        'matplotlib',
        'tkinter',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'tornado',
        'sphinx',
        'pytest',
        'setuptools',
        '_pytest',
        'pygments',
        'jinja2',
        'docutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================================================
# COMPILAÇÃO
# ============================================================================

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OWPICK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # True = mostra console / False = sem console (apenas para apps GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icone.ico',  # Remova esta linha se não tiver o arquivo icone.ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OWPick',
)
