@echo off
setlocal
cd /d "%~dp0"
call Start.cmd --setup
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe build_release.py
if errorlevel 1 goto fail
 echo.
 echo SUCCESS: dist\LumaFlow\LumaFlow.exe
 echo Share the versioned LumaFlow-Windows ZIP in dist with other Windows users.
 echo Keep the entire extracted folder, not just the EXE.
 pause
 exit /b 0
:fail
 echo Build failed. Copy the error above for troubleshooting.
 pause
 exit /b 1
