@echo off
setlocal
cd /d "%~dp0app"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
call setup_media_tools.bat
if errorlevel 1 if not errorlevel 2 echo Media tools are not ready; video streaming may need manual setup.
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8080
endlocal
