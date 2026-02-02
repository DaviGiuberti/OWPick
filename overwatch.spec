# -*- mode: python ; coding: utf-8 -*-
"""
Arquivo de especificação do PyInstaller para Overwatch Helper
Autor: [Seu Nome]
Versão: 1.0
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Inclui a pasta com templates de imagens dos heróis
        ('heroes', 'heroes'),
        
        # Inclui as planilhas de dados (sinergias e counters)
        ('heroes ally.xlsx', '.'),
        ('heroes enemy.xlsx', '.'),
        
        # Se você tiver ChromeDriver, descomente a linha abaixo:
        # ('chromedriver.exe', '.'),
    ],
    hiddenimports=[
        # Bibliotecas principais
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
        'keyboard',
        
        # Seus módulos Python
        'choose_ow_hero',
        'comparar',
        'favoriteHero',
        'map',
        'retirarWinrate',
        'roles',
        'screenshot',
        'site_scrapper',
        
        # Dependências adicionais que podem ser necessárias
        'unicodedata',
        'difflib',
        'pathlib',
        'json',
        'html',
        're',
        'time',
        'threading',
        'math',
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Overwatch Best Pick',
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
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Overwatch Best Pick',
)
