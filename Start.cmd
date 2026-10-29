@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto dependencies
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3 -m venv .venv
if not errorlevel 1 goto dependencies
:python_fallback
python -m venv .venv
if errorlevel 1 goto fail
:dependencies
.venv\Scripts\python.exe -c "import PySide6.QtWidgets, bleak, mss, numpy, pyaudiowpatch, openrgb" >nul 2>nul
if not errorlevel 1 goto launch
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
:launch
if /I "%~1"=="--setup" exit /b 0
.venv\Scripts\python.exe app.py
if errorlevel 1 goto fail
exit /b 0
:fail
 echo.
 echo Setup or launch failed. The error is shown above.
 echo Install 64-bit Python 3.13 with Add Python to PATH enabled.
 echo If upgrading from v0.1, extract v0.3 into its own folder.
 pause
 exit /b 1
