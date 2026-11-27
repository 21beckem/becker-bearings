@echo off
setlocal

set "TOOLS_DIR=%~dp0"
set "PYTHON=%TOOLS_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo The audio-generation environment is missing.
    echo Run tools\audio_generation\setup.bat first.
    exit /b 1
)

"%PYTHON%" "%TOOLS_DIR%generate.py" %*
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
