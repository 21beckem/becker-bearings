@ECHO off
set PYTHONPATH=src
if not exist "%~dp0.venv\Scripts\python.exe" (
    call activate.bat
)
python -m interface.run %*