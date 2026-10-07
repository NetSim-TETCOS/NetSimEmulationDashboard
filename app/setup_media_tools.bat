@echo off
setlocal
cd /d "%~dp0"

echo NetSim media tool setup
echo -----------------------
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_media_tools.ps1" -Check
if not errorlevel 1 goto :ready

echo This project needs FFmpeg 9.0.2 Essentials for TCP / HLS video and MediaMTX 1.21.1 for UDP / WebRTC video.
choice /C YN /N /M "Download and install the pinned tools now? [Y/N]: "
if errorlevel 2 (
  echo Setup skipped. Install the tools manually or set FFMPEG_PATH and MEDIAMTX_PATH in app\.env.
  exit /b 2
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_media_tools.ps1" -Install
if errorlevel 1 (
  echo.
  echo Media tool setup failed. Install FFmpeg 9.0.2 Essentials and MediaMTX 1.21.1 manually,
  echo or set FFMPEG_PATH and MEDIAMTX_PATH in app\.env, then run this file again.
  exit /b 1
)

:ready
if not exist "%~dp0.env" if exist "%~dp0.env.example" copy /Y "%~dp0.env.example" "%~dp0.env" >nul
echo Media tools are ready.
exit /b 0
