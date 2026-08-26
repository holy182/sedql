@echo off
REM SEDQL Build Script for Windows

echo ================================
echo   SEDQL Build Script v2.0
echo ================================
echo.

REM Get project root
set PROJECT_ROOT=%~dp0..
cd %PROJECT_ROOT%

echo Project Root: %CD%
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found
    exit /b 1
)

echo Using Python: 
python --version
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.egg-info rmdir /s /q *.egg-info
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
echo Clean complete
echo.

REM Install build dependencies
echo Installing build dependencies...
python -m pip install --upgrade pip setuptools wheel build twine
echo.

REM Install project dependencies
echo Installing project dependencies...
if exist requirements.txt (
    python -m pip install -r requirements.txt
    echo Requirements installed
)
echo.

REM Install in development mode
echo Installing SEDQL in development mode...
python -m pip install -e .
echo Development installation complete
echo.

REM Build package
echo Building package...
python -m build
echo Build complete
echo.

REM Check package
echo Checking package...
python -m twine check dist/*
echo.

echo ================================
echo Build Complete!
echo ================================
echo.
echo   Package: dist/sedql-*.whl
echo   Source: dist/sedql-*.tar.gz
echo.
echo To install:
echo   pip install dist/sedql-*.whl
echo.
echo To test:
echo   sedql --help
echo.

pause