@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0textile_project"

rem textile batch: every design pair in textile_project\input, filled with
rem --method auto: NAME_lineart.png with NAME_ref.png (or NAME_colored.png),
rem png, jpg or tif. Results go to textile_project\output\NAME\ and
rem output\batch_summary.csv. Other commands (repeat, tile, make, vector):
rem   .venv\Scripts\python.exe -m textile --help   (inside textile_project)

set PYEXE=
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe
if not defined PYEXE if exist "C:\Program Files\Python313\python.exe" set PYEXE=C:\Program Files\Python313\python.exe
if not defined PYEXE if exist "C:\Program Files\Python312\python.exe" set PYEXE=C:\Program Files\Python312\python.exe
if not defined PYEXE if exist "C:\Program Files\Python311\python.exe" set PYEXE=C:\Program Files\Python311\python.exe
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

if not exist .venv (
  echo Textile tool setup ho raha hai, ek baar hi hoga, thoda time lagega...
  "%PYEXE%" -m venv .venv
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  ".venv\Scripts\python.exe" -c "import numpy, cv2, PIL, scipy, sklearn" 2>nul
  if errorlevel 1 (
    echo [ERROR] Install nahi hua -- internet chahiye pehli baar. Upar ka message Claude ko bhejo.
    pause
    exit /b 1
  )
)

if not exist input mkdir input
if not exist output mkdir output
".venv\Scripts\python.exe" -m textile batch input --out output
if errorlevel 1 (
  echo.
  echo Kuch designs ruke ya jaanch maangte hain -- upar ki table aur output\batch_summary.csv dekho.
)
start "" "%~dp0textile_project\output"
pause
endlocal
