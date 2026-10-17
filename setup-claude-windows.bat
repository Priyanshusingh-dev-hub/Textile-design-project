@echo off
rem LoomLab ko Claude se jodo: Claude khud designs chala sake, proof dekh sake,
rem jobs approve/reject kar sake. Pehle run-windows.bat ek baar chal chuka ho.
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Pehle run-windows.bat ek baar chalao, phir ye file.
  pause
  exit /b 1
)

cd backend
".venv\Scripts\python.exe" -m app.mcp_server --install-desktop
if errorlevel 1 (
  echo [ERROR] Upar ka message Claude ko bhejo.
  pause
  exit /b 1
)
echo.
echo Claude Code (terminal) wale ke liye ye bhi:
".venv\Scripts\python.exe" -m app.mcp_server --setup
pause
endlocal
