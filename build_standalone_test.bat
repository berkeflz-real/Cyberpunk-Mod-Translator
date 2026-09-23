@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_NAME=Cyberpunk 2077 Universal Mod Translator"
set "OUTPUT_DIR=%CD%\build_nuitka_test"

if not exist "app.py" (
    echo ERROR: app.py was not found in this folder.
    pause
    exit /b 1
)
if not exist "translator.py" (
    echo ERROR: translator.py was not found in this folder.
    pause
    exit /b 1
)
if not exist "WolvenKit.Console-9.0.1\WolvenKit.CLI.exe" (
    echo ERROR: WolvenKit.Console-9.0.1\WolvenKit.CLI.exe was not found.
    pause
    exit /b 1
)

python -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Nuitka is not installed for this Python.
    echo Install it with: python -m pip install Nuitka
    pause
    exit /b 1
)

if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
mkdir "%OUTPUT_DIR%"

echo.
echo ============================================================
echo NUITKA STANDALONE TEST BUILD
echo ============================================================
echo.

python -m nuitka ^
    --mode=standalone ^
    --windows-console-mode=disable ^
    --enable-plugin=tk-inter ^
    --follow-imports ^
    --output-dir="%OUTPUT_DIR%" ^
    --output-filename="%APP_NAME%.exe" ^
    "app.py"

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

xcopy /E /I /Y "WolvenKit.Console-9.0.1" "%OUTPUT_DIR%\%APP_NAME%.dist\WolvenKit.Console-9.0.1" >nul
if exist "LICENSE-NOTICE.txt" copy /Y "LICENSE-NOTICE.txt" "%OUTPUT_DIR%\%APP_NAME%.dist\" >nul
if exist "THIRD-PARTY-NOTICES.txt" copy /Y "THIRD-PARTY-NOTICES.txt" "%OUTPUT_DIR%\%APP_NAME%.dist\" >nul

if exist "%OUTPUT_DIR%\%APP_NAME%.dist\%APP_NAME%.exe" (
    echo.
    echo STANDALONE BUILD COMPLETED.
    echo Test this file first:
    echo %OUTPUT_DIR%\%APP_NAME%.dist\%APP_NAME%.exe
    echo.
    echo Keep WolvenKit.Console-9.0.1 next to the EXE while testing.
) else (
    echo ERROR: Expected executable was not produced.
)
pause
endlocal
