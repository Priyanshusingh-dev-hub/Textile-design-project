@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem Already running (its window is still open): just open the app. Starting a
rem second engine would fail on the port while this script opened the old one
rem with a freshly built page -- an old engine behind a new app.
curl -s -o nul http://localhost:8003/api/health
if not errorlevel 1 (
  echo LoomLab pehle se chal raha hai -- browser khol raha hoon.
  echo Update ke baad: "LoomLab" wali kaali window band karo, phir ye file dobara chalao.
  start http://localhost:8003
  timeout /t 5 >nul
  exit /b 0
)

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

echo Python mil gaya: %PYEXE%
if defined NODEDIR echo Node.js mil gaya: %NODEDIR%
echo.

cd backend
if not exist .venv (
  echo Backend setup ho raha hai, ek baar hi hoga, thoda time lagega...
  "%PYEXE%" -m venv .venv
)
echo Backend dependencies check ho rahe hain, naye ho to install honge...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  rem offline is fine if everything is already installed; only stop if the engine can't import
  ".venv\Scripts\python.exe" -c "import fastapi, uvicorn, numpy, PIL, scipy" 2>nul
  if errorlevel 1 (
    echo [ERROR] Backend install nahi hua -- internet chahiye pehli baar. Upar ka message Claude ko bhejo.
    pause
    exit /b 1
  )
)
cd ..

rem The app is built once by Node, then the engine serves it itself: one
rem server, one window, one address. Without Node, an app built earlier runs.
rem ("call" matters: a .cmd run from a .bat without it never comes back.)
if not defined NODEDIR goto :nonode
cd frontend
if not exist node_modules (
  echo Frontend setup ho raha hai, ek baar hi hoga, thoda time lagega...
  call "%NODEDIR%\npm.cmd" install
)
echo App taiyaar ho raha hai...
call "%NODEDIR%\npm.cmd" run build
if errorlevel 1 (
  rem an update may need packages this PC doesn't have yet: fetch them, try once more
  echo Naye packages aa rahe hain...
  call "%NODEDIR%\npm.cmd" install
  call "%NODEDIR%\npm.cmd" run build
)
if errorlevel 1 (
  echo [ERROR] App build nahi hua. Upar ka message Claude ko bhejo.
  pause
  exit /b 1
)
cd ..
goto :engine

:nonode
if exist "frontend\dist\index.html" goto :engine
echo.
echo [ERROR] Node.js nahi mil raha, aur app pehle kabhi bana nahi. Ye command chalao aur output Claude ko bhejo:
echo   dir "C:\Program Files\nodejs"
pause
exit /b 1

:engine
start "LoomLab" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\uvicorn.exe app.main:app --port 8003"

echo.
echo LoomLab start ho raha hai. Engine ready hote hi browser khulega, max 60 second...
rem Wait until the engine answers, instead of guessing: a first run or a slow
rem PC can take longer than a fixed pause, and the page would open to an error.
for /l %%i in (1,1,60) do (
  curl -s -o nul http://localhost:8003/api/health && goto :ready
  timeout /t 1 /nobreak >nul
)
:ready
start http://localhost:8003

endlocal
