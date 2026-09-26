@echo off
rem LoomLab Telegram inbox: saves every design sent to the bot on this PC.
rem Needs only Python (no LoomLab install). Settings: telegram-bot.txt here.
setlocal
cd /d "%~dp0"

set PYEXE=
if exist "backend\.venv\Scripts\python.exe" set PYEXE=%~dp0backend\.venv\Scripts\python.exe
if not defined PYEXE (
  for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set PYEXE=%%P
)
if not defined PYEXE (
  for /f "delims=" %%P in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PYEXE set PYEXE=%%P
)
if not defined PYEXE (
  echo [ERROR] Python nahi mil raha. Pehle run-windows.bat ek baar chalao.
  pause
  exit /b 1
)

cd backend
"%PYEXE%" -m app.inbox_bot "%~dp0telegram-bot.txt"
if errorlevel 2 (
  rem Token missing or wrong: open the settings so it can be filled in.
  start notepad "%~dp0telegram-bot.txt"
)
pause
endlocal
