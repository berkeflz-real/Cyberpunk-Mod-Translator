@echo off
title Building Release

cd /d "%~dp0"

echo ==========================================
echo Building Cyberpunk Mod Translator...
echo ==========================================

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__

pyinstaller --clean --noconfirm "Cyberpunk Mod Translator.spec"
echo.
echo ==========================================
echo BUILD FINISHED
echo ==========================================
pause