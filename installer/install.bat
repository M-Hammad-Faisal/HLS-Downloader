@echo off
setlocal enabledelayedexpansion

:: HLS Downloader - Smart Windows Installer
:: This script downloads, builds, and installs HLS Downloader automatically
echo ========================================
echo HLS Downloader - Smart Installer
echo ========================================
echo.

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with administrator privileges...
) else (
    echo Note: Some operations may require administrator privileges
)

:: Set variables
set "INSTALL_DIR=%USERPROFILE%\HLS-Downloader"
set "TEMP_DIR=%TEMP%\hls-installer"
set "PYTHON_VERSION=3.11.7"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "REPO_URL=https://github.com/M-Hammad-Faisal/HLS-Downloader/archive/refs/heads/master.zip"

echo Installing to: %INSTALL_DIR%
echo.

:: Create directories
echo [1/8] Creating installation directories...
if exist "%INSTALL_DIR%" (
    echo Removing existing installation...
    rmdir /s /q "%INSTALL_DIR%" 2>nul
)
mkdir "%INSTALL_DIR%" 2>nul
mkdir "%TEMP_DIR%" 2>nul

:: Download portable Python
echo [2/8] Downloading portable Python %PYTHON_VERSION%...
cd /d "%TEMP_DIR%"
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile 'python.zip'}"
if not exist "python.zip" (
    echo ERROR: Failed to download Python
    goto :error
)

:: Extract Python
echo [3/8] Extracting portable Python...
powershell -Command "Expand-Archive -Path 'python.zip' -DestinationPath '%INSTALL_DIR%\python' -Force"
if not exist "%INSTALL_DIR%\python\python.exe" (
    echo ERROR: Failed to extract Python
    goto :error
)

:: Configure Python
echo [4/8] Configuring Python environment...
cd /d "%INSTALL_DIR%\python"
echo import site > python311._pth
echo . >> python311._pth
echo .\Lib\site-packages >> python311._pth

:: Download get-pip
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'}"
python.exe get-pip.py --no-warn-script-location
del get-pip.py

:: Download source code
echo [5/8] Downloading HLS Downloader source code...
cd /d "%TEMP_DIR%"
powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_URL%' -OutFile 'source.zip'}"
if not exist "source.zip" (
    echo ERROR: Failed to download source code
    goto :error
)

:: Extract source code
powershell -Command "Expand-Archive -Path 'source.zip' -DestinationPath '.' -Force"
if not exist "HLS-Downloader-master" (
    echo ERROR: Failed to extract source code
    goto :error
)

:: Install dependencies
echo [6/8] Installing Python dependencies...
cd /d "%TEMP_DIR%\HLS-Downloader-master"
"%INSTALL_DIR%\python\python.exe" -m pip install -r requirements.txt --no-warn-script-location

:: Install PyInstaller
"%INSTALL_DIR%\python\python.exe" -m pip install pyinstaller --no-warn-script-location

:: Install Playwright browsers
echo Installing Playwright browsers...
"%INSTALL_DIR%\python\python.exe" -m playwright install chromium

:: Build the application
echo [7/8] Building HLS Downloader application...
"%INSTALL_DIR%\python\python.exe" -m PyInstaller --onefile --windowed --name "HLS-Downloader" --icon "assets\icon.ico" --add-data "assets;assets" main.py

if not exist "dist\HLS-Downloader.exe" (
    echo ERROR: Failed to build application
    goto :error
)

:: Copy built application and browsers
echo [8/8] Finalizing installation...
copy "dist\HLS-Downloader.exe" "%INSTALL_DIR%\" >nul
xcopy /s /e /i "%USERPROFILE%\.cache\ms-playwright" "%INSTALL_DIR%\browsers" >nul 2>&1

:: Create launcher script
echo @echo off > "%INSTALL_DIR%\HLS-Downloader.bat"
echo cd /d "%%~dp0" >> "%INSTALL_DIR%\HLS-Downloader.bat"
echo set PLAYWRIGHT_BROWSERS_PATH=%%~dp0browsers >> "%INSTALL_DIR%\HLS-Downloader.bat"
echo HLS-Downloader.exe >> "%INSTALL_DIR%\HLS-Downloader.bat"

:: Create desktop shortcut
echo Creating desktop shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\HLS Downloader.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\HLS-Downloader.bat'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.IconLocation = '%INSTALL_DIR%\HLS-Downloader.exe'; $Shortcut.Save()"

:: Cleanup
echo Cleaning up temporary files...
cd /d "%USERPROFILE%"
rmdir /s /q "%TEMP_DIR%" 2>nul
rmdir /s /q "%INSTALL_DIR%\python" 2>nul

echo.
echo ========================================
echo Installation completed successfully!
echo ========================================
echo.
echo HLS Downloader has been installed to:
echo %INSTALL_DIR%
echo.
echo You can run it from:
echo - Desktop shortcut: "HLS Downloader"
echo - Direct: %INSTALL_DIR%\HLS-Downloader.bat
echo.
echo The application includes all necessary browsers and dependencies.
echo No additional setup required!
echo.
pause
goto :end

:error
echo.
echo ========================================
echo Installation failed!
echo ========================================
echo.
echo Please check your internet connection and try again.
echo If the problem persists, please report it on GitHub.
echo.
pause

:end
endlocal