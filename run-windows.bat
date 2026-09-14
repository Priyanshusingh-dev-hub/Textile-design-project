@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set PYEXE=
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe
if not defined PYEXE if exist "C:\Program Files\Python313\python.exe" set PYEXE=C:\Program Files\Python313\python.exe
if not defined PYEXE if exist "C:\Program Files\Python312\python.exe" set PYEXE=C:\Program Files\Python312\python.exe
if not defined PYEXE (
  echo.
  echo [ERROR] Python nahi mil raha. Ye command chalao aur output Claude ko bhejo:
  echo   dir "%LocalAppData%\Programs\Python"
  pause
  exit /b 1
)

set NODEDIR=
if exist "C:\Program Files\nodejs\node.exe" set NODEDIR=C:\Program Files\nodejs
if not defined NODEDIR if exist "C:\Program Files (x86)\nodejs\node.exe" set NODEDIR=C:\Program Files (x86)\nodejs
if not defined NODEDIR (
  echo.
  echo [ERROR] Node.js nahi mil raha. Ye command chalao aur output Claude ko bhejo:
  echo   dir "C:\Program Files\nodejs"
  pause
  exit /b 1
)

echo Python mil gaya: %PYEXE%
echo Node.js mil gaya: %NODEDIR%
echo.

cd backend
if not exist .venv (
  echo Backend setup ho raha hai, ek baar hi hoga, thoda time lagega...
  "%PYEXE%" -m venv .venv
  ".venv\Scripts\pip.exe" install -r requirements.txt
)
start "LoomLab Backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\uvicorn.exe app.main:app --reload --port 8003"
cd ..

cd frontend
if not exist node_modules (
  echo Frontend setup ho raha hai, ek baar hi hoga, thoda time lagega...
  "%NODEDIR%\npm.cmd" install
)
start "LoomLab Frontend" cmd /k "cd /d "%~dp0frontend" && "%NODEDIR%\npm.cmd" run dev"
cd ..

echo.
echo Dono server start ho gaye. 8 second mein browser khulega...
timeout /t 8 /nobreak >nul
start http://localhost:5173

endlocal
