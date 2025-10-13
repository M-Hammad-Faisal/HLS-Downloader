@echo off
title HLS Downloader Installer
color 0A

echo.
echo ========================================
echo    HLS Downloader Smart Installer
echo ========================================
echo.
echo This installer will:
echo - Check for Python 3.8+
echo - Download HLS Downloader
echo - Set up environment
echo - Install dependencies
echo - Create desktop shortcut
echo.
echo Installation size: ~5-10MB (downloads ~50MB)
echo Final app size: ~200MB (vs 800MB bundled)
echo.
pause

:: Check if Python is installed
echo Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Checking for python3...
    python3 --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: Python 3.8+ is required but not found.
        echo.
        echo Please install Python from: https://python.org/downloads
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=python3
    )
) else (
    set PYTHON_CMD=python
)

:: Check Python version
echo Checking Python version...
%PYTHON_CMD% -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python 3.8 or higher is required.
    echo Please update Python from: https://python.org/downloads
    echo.
    pause
    exit /b 1
)

echo Python found and compatible!

:: Set installation directory
set INSTALL_DIR=%LOCALAPPDATA%\HLS Downloader
echo Installing to: %INSTALL_DIR%

:: Create installation directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Download the Python installer script
echo.
echo Downloading installer script...
powershell -Command "& {Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/M-Hammad-Faisal/HLS-Downloader/master/installer/install.py' -OutFile '%INSTALL_DIR%\install.py'}"

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to download installer script.
    echo Please check your internet connection.
    echo.
    pause
    exit /b 1
)

:: Run the Python installer
echo.
echo Running installation...
cd /d "%INSTALL_DIR%"
%PYTHON_CMD% install.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Installation failed.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo    Installation Complete!
echo ========================================
echo.
echo HLS Downloader has been installed successfully.
echo You can find it in your Start Menu or Desktop.
echo.
pause