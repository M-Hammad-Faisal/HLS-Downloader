@echo off
title HLS Video Downloader - Installer

echo ========================================
echo  HLS Video Downloader - Smart Installer
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python 3.8 or higher from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Python found. Starting installation...
echo.

REM Run the Python installer
python installer.py

if errorlevel 1 (
    echo.
    echo Installation failed!
    pause
    exit /b 1
)

echo.
echo Installation completed successfully!
echo You can now close this window.
pause