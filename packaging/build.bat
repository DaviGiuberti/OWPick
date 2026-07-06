@echo off
setlocal EnableDelayedExpansion
REM ===========================================================================
REM build.bat — Build completo do OWPick
REM ===========================================================================
REM Gera, nesta ordem:
REM   1. dist\OWPick\                (PyInstaller one-folder, via overwatch.spec)
REM   2. dist\OWPick_v<versao>.zip   (pacote consumido pelo auto-updater)
REM   3. dist\OWPick Installer.exe   (instalador Inno Setup p/ novos usuarios)
REM
REM Distribuicao (GitHub Releases):
REM   - Novos usuarios baixam apenas "OWPick Installer.exe".
REM   - O auto-updater baixa o .zip (URL em version.json).
REM ===========================================================================

REM Este script vive em packaging/; o build roda a partir da RAIZ do repo.
cd /d "%~dp0.."

REM Forca UTF-8 no Python (o .spec imprime caracteres Unicode no log)
set PYTHONUTF8=1

REM --- Versao (fonte unica: version.txt) ---
set /p VERSION=<version.txt
echo [build] Versao: %VERSION%

REM --- Python: prefere o venv do projeto ---
set PYTHON=python
if exist ".venv\Scripts\python.exe" set PYTHON=.venv\Scripts\python.exe

REM --- Localiza o compilador do Inno Setup ---
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo [build] ERRO: Inno Setup 6 nao encontrado. Instale em https://jrsoftware.org/isdl.php
    exit /b 1
)

REM --- 1. PyInstaller ---
echo [build] Gerando executavel com PyInstaller...
"%PYTHON%" -m PyInstaller packaging\overwatch.spec --noconfirm
if errorlevel 1 (
    echo [build] ERRO: falha no PyInstaller.
    exit /b 1
)

REM --- 2. Zip de update (mesmo formato que o updater.py espera) ---
echo [build] Compactando pacote de update dist\OWPick_v%VERSION%.zip...
if exist "dist\OWPick_v%VERSION%.zip" del /f /q "dist\OWPick_v%VERSION%.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\OWPick' -DestinationPath 'dist\OWPick_v%VERSION%.zip' -Force"
if errorlevel 1 (
    echo [build] ERRO: falha ao compactar o pacote de update.
    exit /b 1
)

REM --- 3. Instalador (Inno Setup) ---
echo [build] Compilando instalador...
"%ISCC%" /Q packaging\installer.iss
if errorlevel 1 (
    echo [build] ERRO: falha ao compilar o instalador.
    exit /b 1
)

echo.
echo [build] Concluido com sucesso:
echo   dist\OWPick\                    (build bruto)
echo   dist\OWPick_v%VERSION%.zip      (pacote do auto-updater)
echo   dist\OWPick Installer.exe       (distribuicao p/ novos usuarios)
endlocal
