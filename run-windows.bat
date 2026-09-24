@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set PYEXE=
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe
if not defined PYEXE if exist "C:\Program Files\Python313\python.exe" set PYEXE=C:\Program Files\Python313\python.exe
if not defined PYEXE if exist "C:\Program Files\Python312\python.exe" set PYEXE=C:\Program Files\Python312\python.exe
if not defined PYEXE if exist "C:\Program Files\Python311\python.exe" set PYEXE=C:\Program Files\Python311\python.exe
rem Fallback: a supported Python (3.11+, which numpy needs) through the py
rem launcher, then any python on the PATH -- skipping the WindowsApps stub,
rem which only opens the Microsoft Store.
for %%V in (3.13 3.12 3.11) do (
  if not defined PYEXE (
    for /f "delims=" %%P in ('py -%%V -c "import sys; print(sys.executable)" 2^>nul') do set PYEXE=%%P
  )
)
if not defined PYEXE (
  for /f "delims=" %%P in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PYEXE set PYEXE=%%P
)
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
rem Fallback: node on the PATH (nvm, portable installs).
if not defined NODEDIR (
  for /f "delims=" %%N in ('where node 2^>nul') do if not defined NODEDIR set NODEDIR=%%~dpN
)
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
)
echo Backend dependencies check ho rahe hain (naye ho to install honge)...
".venv\Scripts\pip.exe" install -q -r requirements.txt
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
echo Dono server start ho rahe hain. Engine ready hote hi browser khulega (max 60 second)...
rem Wait until the engine answers, instead of guessing: a first run or a slow
rem PC can take longer than a fixed pause, and the page would open to an error.
for /l %%i in (1,1,60) do (
  curl -s -o nul http://localhost:8003/api/health && goto :ready
  timeout /t 1 /nobreak >nul
)
:ready
timeout /t 2 /nobreak >nul
start http://localhost:5173

endlocal
