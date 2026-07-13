@echo off
REM Build script for KingsTrial executable
REM This script creates a standalone executable using PyInstaller

echo Building KingsTrial executable...
echo.

REM Clean previous builds
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.spec del *.spec

echo Cleaned previous build artifacts.
echo.

REM Run PyInstaller
echo Running PyInstaller...
python -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name "KingsTrial" ^
  --icon "assets\themes\default.json" ^
  --hidden-import=scenes ^
  --hidden-import=ai ^
  --hidden-import=ui ^
  --collect-all=pygame ^
  --add-data "assets;assets" ^
  --add-data "config.json;." ^
  main.py

if errorlevel 1 (
  echo.
  echo Build failed!
  pause
  exit /b 1
)

echo.
echo Build completed successfully!
echo Executable created at: dist\KingsTrial.exe
echo.
pause
