@echo off
REM ============================================================
REM  build.bat — eStamp Ninja Secure Build Script
REM  VYRON (Not Noise. Signal)
REM
REM  Steps:
REM    1. Install build dependencies
REM    2. Obfuscate source with PyArmor
REM    3. Bundle into single EXE with PyInstaller
REM ============================================================

setlocal
set PROJECT=%~dp0
set DIST=%PROJECT%dist
set BUILD_TMP=%PROJECT%_build_tmp

echo.
echo ============================================================
echo   eStamp Ninja ^| Secure Build
echo   VYRON (Not Noise. Signal)
echo ============================================================
echo.

REM ── Step 1: Install dependencies ─────────────────────────────────────────────
echo [1/4] Installing build dependencies...
py -m pip install pyinstaller pyarmor cryptography playwright pillow --quiet
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Check your Python/pip setup.
    goto :fail
)
echo       Done.
echo.

REM ── Step 2: Convert icon.png to icon.ico ─────────────────────────────────────
echo [2/4] Converting icon...
py -c "from PIL import Image; img=Image.open(r'%PROJECT%icon.png'); img.save(r'%PROJECT%icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])"
if %ERRORLEVEL% neq 0 (
    echo WARNING: icon conversion failed. Building without custom icon.
    set ICON_ARG=
) else (
    set ICON_ARG=--icon "%PROJECT%icon.ico"
)
echo       Done.
echo.

REM ── Step 3: Obfuscate with PyArmor ───────────────────────────────────────────
echo [3/4] Obfuscating source with PyArmor...
if exist "%BUILD_TMP%" rmdir /s /q "%BUILD_TMP%"
mkdir "%BUILD_TMP%"

REM Obfuscate the entry point and all local modules
py -m pyarmor gen --output "%BUILD_TMP%" ^
    "%PROJECT%estamp_auto.py" ^
    "%PROJECT%license_core.py" ^
    "%PROJECT%ui.py" ^
    "%PROJECT%automation.py" ^
    "%PROJECT%config.py"

if %ERRORLEVEL% neq 0 (
    echo ERROR: PyArmor obfuscation failed.
    goto :fail
)
echo       Done.
echo.

REM ── Step 4: Bundle with PyInstaller ──────────────────────────────────────────
echo [4/4] Bundling EXE with PyInstaller...

REM Copy non-Python assets into build temp
copy "%PROJECT%icon.png" "%BUILD_TMP%\" >nul
copy "%PROJECT%logo.png" "%BUILD_TMP%\" >nul

py -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "eStampNinja" ^
    %ICON_ARG% ^
    --add-data "%BUILD_TMP%\icon.png;." ^
    --add-data "%BUILD_TMP%\logo.png;." ^
    --hidden-import playwright ^
    --hidden-import playwright.sync_api ^
    --hidden-import cryptography ^
    --hidden-import cryptography.fernet ^
    --distpath "%DIST%" ^
    --workpath "%PROJECT%_pyi_work" ^
    --specpath "%BUILD_TMP%" ^
    "%BUILD_TMP%\estamp_auto.py"

if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller build failed.
    goto :fail
)

REM ── Cleanup ───────────────────────────────────────────────────────────────────
rmdir /s /q "%PROJECT%_pyi_work" >nul 2>&1
rmdir /s /q "%BUILD_TMP%" >nul 2>&1

echo.
echo ============================================================
echo   SUCCESS!
echo   EXE Location: %DIST%\eStampNinja.exe
echo   Chromium auto-installs on first client launch.
echo ============================================================
echo.
goto :end

:fail
echo.
echo ============================================================
echo   BUILD FAILED — see errors above.
echo ============================================================
echo.
exit /b 1

:end
endlocal
pause
