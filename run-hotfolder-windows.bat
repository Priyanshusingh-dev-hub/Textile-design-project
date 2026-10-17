@echo off
rem LoomLab Hot Folder: Hot-Folder\in me design daalo, screens + proof + quote
rem apne aap Hot-Folder\ready (ya dekhne wale Hot-Folder\check) me aa jaayenge.
rem LoomLab (run-windows.bat) bhi chalu rehna chahiye.
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Pehle run-windows.bat ek baar chalao, phir ye file.
  pause
  exit /b 1
)

if not exist "Hot-Folder\in" mkdir "Hot-Folder\in"
start "" explorer "%~dp0Hot-Folder"
cd backend
rem Default print width / meters for files whose name gives none: add e.g. --width-in 30 --meters 500
".venv\Scripts\python.exe" -m app.hot_folder "%~dp0Hot-Folder"
pause
endlocal
