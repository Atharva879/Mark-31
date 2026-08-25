@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ================================================
echo   Mark-31 Jarvis - Dependency Installer
echo ================================================
echo.

echo Checking for Python 3.11 or newer...
py -3.11 -c "import sys; assert sys.version_info >= (3,11), sys.version; print(sys.version)"
if errorlevel 1 (
    echo.
    echo ERROR: Python 3.11 or newer was not found through the Windows Python launcher.
    echo Install Python from https://www.python.org/downloads/windows/
    echo Make sure the Python launcher and pip are enabled, then run this file again.
    goto :failed
)

echo.
echo Upgrading pip...
py -3.11 -m pip install --upgrade pip
if errorlevel 1 goto :pip_failed

echo.
echo Installing Mark-31 core, provider, Windows, multimodal, voice, and development packages...
py -3.11 -m pip install -e ".[providers,windows,multimodal,voice,dev]"
if errorlevel 1 goto :pip_failed

echo.
echo Installing Playwright Chromium browser binaries...
py -3.11 -m playwright install chromium
if errorlevel 1 goto :playwright_failed

echo.
echo Running a quick Mark-31 import check...
py -3.11 -c "import main, ui, interactive_browser, desktop_control; print('Mark-31 imports: OK')"
if errorlevel 1 goto :failed

echo.
echo ================================================
echo   Dependencies installed successfully.
echo ================================================
echo.
echo You can now run build_windows.ps1 from PowerShell:
echo   powershell.exe -ExecutionPolicy Bypass -File .\build_windows.ps1
pause
exit /b 0

:pip_failed
echo.
echo ERROR: Python package installation failed.
echo Check your internet connection and the Python/pip error above.
goto :failed

:playwright_failed
echo.
echo ERROR: Playwright Chromium installation failed.
echo Check your internet connection and run this installer again.
goto :failed

:failed
echo.
echo Mark-31 dependency installation did not complete.
pause
exit /b 1
