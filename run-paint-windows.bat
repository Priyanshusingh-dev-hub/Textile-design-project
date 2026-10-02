@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0textile_project"

rem textile paint: a sketch (line art) coloured the way YOU say, one channel per colour.
rem Drag the sketch onto this file.
rem   1st time: the map (letters on every part) and NAME_colors.txt open. Write the colours
rem             (A = cream, B = laal, lines = coffee ...), save, close.
rem   2nd time: drag the same sketch again: the design + TIF for the mill + channels.
rem Results: textile_project\output\paint\<sketch name>\

if "%~1"=="" (
  echo Sketch ki file is .bat par drag karke chhodo.
  pause
  exit /b 1
)

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

set "OUT=%~dp0textile_project\output\paint\%~n1"
if not exist "%OUT%" mkdir "%OUT%"
".venv\Scripts\python.exe" -m textile paint "%~1" --out "%OUT%"
if errorlevel 1 (
  echo.
  echo Ruk gaya -- upar ka STOP wala message padho, ya Claude ko bhejo.
  pause
  exit /b 1
)
if exist "%OUT%\*_final_*.tif" (
  start "" "%OUT%"
) else (
  for %%F in ("%OUT%\*_map.png") do start "" "%%F"
  for %%F in ("%OUT%\*_colors.txt") do start "" notepad "%%F"
  echo.
  echo Map dekho, NAME_colors.txt me rang likho, save karo, phir wahi sketch dobara is .bat par chhodo.
)
pause
endlocal
