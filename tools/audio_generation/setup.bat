@echo off
setlocal

set "TOOLS_DIR=%~dp0"
set "VENV_DIR=%TOOLS_DIR%.venv"
set "PYTHON_CMD="
set "UV_CMD="

where uv >nul 2>&1
if not errorlevel 1 set "UV_CMD=uv"
set "UV_CACHE_DIR=%TEMP%\becker-bearings-audio-uv-cache"

for %%P in (python3.12 python3.11 python3.10) do (
    where %%P >nul 2>&1
    if not errorlevel 1 if not defined PYTHON_CMD set "PYTHON_CMD=%%P"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if errorlevel 1 (
        echo A supported Python installation was not found on PATH.
        echo Install Python 3.12, 3.11, or 3.10 and ensure its command is available.
        exit /b 1
    )
    python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)"
    if errorlevel 1 (
        echo Python 3.13 cannot install the Kokoro generation dependencies.
        echo Install Python 3.12, 3.11, or 3.10 for the separate audio tools.
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

set "RECREATE_VENV=0"
if not exist "%VENV_DIR%\Scripts\python.exe" set "RECREATE_VENV=1"
if exist "%VENV_DIR%\Scripts\python.exe" (
    "%VENV_DIR%\Scripts\python.exe" -c "import sys; import pip; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)" >nul 2>&1
    if errorlevel 1 set "RECREATE_VENV=1"
)

if "%RECREATE_VENV%"=="1" (
    echo Creating the isolated audio-generation environment with %PYTHON_CMD%...
    if defined UV_CMD (
        "%UV_CMD%" venv --python "%PYTHON_CMD%" --seed --clear "%VENV_DIR%"
    ) else (
        "%PYTHON_CMD%" -m venv --clear "%VENV_DIR%"
    )
    if errorlevel 1 exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Failed to create the audio-generation environment.
    exit /b 1
)

echo Installing audio-generation dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%TOOLS_DIR%requirements.txt"
if errorlevel 1 exit /b 1

echo.
echo Audio-generation tools are ready.
echo Run generate.bat to create WAV assets.
endlocal
