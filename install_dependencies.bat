@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ================================================
echo   Mark-31 Jarvis - Dependency Installer
echo ================================================
echo.

echo Checking for Python 3.11 or newer...
set "PYTHON="
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if not defined PYTHON for /f "delims=" %%P in ('where python3 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if not defined PYTHON for /f "delims=" %%P in ('where py 2^>nul') do if not defined PYTHON set "PYTHON=%%P"

if not defined PYTHON (
    echo.
    echo ERROR: No Python executable was found on PATH.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
    goto :failed
)

"%PYTHON%" -c "import sys; print('Using Python', sys.version); raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo.
    echo ERROR: The detected Python is older than 3.11.
    echo Install Python 3.11 or newer and run this file again.
    goto :failed
)

echo.
echo Upgrading pip...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_failed

echo.
echo Installing Mark-31 core, provider, Windows, multimodal, voice, and development packages...
"%PYTHON%" -m pip install -e ".[providers,windows,multimodal,voice,dev]"
if errorlevel 1 goto :pip_failed

echo.
echo Installing Playwright Chromium browser binaries...
"%PYTHON%" -m playwright install chromium
if errorlevel 1 goto :playwright_failed

echo.
echo Running a quick Mark-31 import check...
"%PYTHON%" -c "import main, ui, interactive_browser, desktop_control; print('Mark-31 imports: OK')"
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
