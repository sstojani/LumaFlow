@echo off
setlocal
cd /d "%~dp0"
call Start.cmd --setup
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install "pyinstaller>=6.12,<7"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name LumaFlow --icon assets/lumaflow.ico --hidden-import orgb_worker --collect-all bleak --collect-all pyaudiowpatch --collect-all openrgb --exclude-module PySide6.QtWebEngineCore app.py
if errorlevel 1 goto fail
powershell -NoProfile -Command "Compress-Archive -Path 'dist\LumaFlow' -DestinationPath 'dist\LumaFlow-Windows.zip' -Force"
if errorlevel 1 goto fail
 echo.
 echo SUCCESS: dist\LumaFlow\LumaFlow.exe
 echo Share dist\LumaFlow-Windows.zip with other Windows users.
 echo Keep the entire extracted folder, not just the EXE.
 pause
 exit /b 0
:fail
 echo Build failed. Copy the error above for troubleshooting.
 pause
 exit /b 1
