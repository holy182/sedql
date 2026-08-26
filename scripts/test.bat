@echo off
REM SEDQL Test Script for Windows

echo ================================
echo   SEDQL Test Script v2.0
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

REM Install test dependencies
echo Installing test dependencies...
python -m pip install pytest pytest-cov
echo.

REM Run tests
echo Running tests with coverage...
python -m pytest tests/ -v --tb=short --cov=src/sedql --cov-report=html --cov-report=term
echo.

echo ================================
echo Test Complete!
echo ================================
echo.
echo Coverage report: htmlcov/index.html
echo.

pause