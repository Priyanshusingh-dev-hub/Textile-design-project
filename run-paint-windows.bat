@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0textile_project"

rem textile paint: a sketch (line art) coloured the way YOU say, one channel per colour.
rem Drag the sketch onto this file.
rem   1st time: the map (a number in every closed part, letters for look-alike parts) and
rem             NAME_colors.txt open. Write the colours (1 = cream, 4 7 = laal, lines = coffee ...),
rem             save, close.
rem   2nd time: drag the same sketch again: the design + TIF for the mill + channels + B/W films.
rem A CSV of colours (columns Number and HEX) works too: drag the sketch AND the CSV together,
rem or keep NAME.csv (or NAME_colors.csv) next to the sketch.
rem A part with no colour takes the nearest part's colour (never white unless you said white).
rem Coloured version of the same design? Name it NAME_ref.png (or NAME_colored.png) and drag it WITH the
rem sketch: every part takes its colour from it (NAME_ref_numbers.png shows the numbers on it).
rem Leaves joining the ground (gaps in the lines)? Rename the sketch NAME_seal10.png (8, 10, 12...).
rem Results: textile_project\output\paint\<sketch name>\

set "SKETCH="
set "CSV="
set "REF="
for %%A in (%*) do (
  set "N=%%~nA"
  if /i "%%~xA"==".csv" (
    set "CSV=%%~fA"
  ) else if not "!N:_ref=!"=="!N!" (
    set "REF=%%~fA"
  ) else if not "!N:_colored=!"=="!N!" (
    set "REF=%%~fA"
  ) else (
    set "SKETCH=%%~fA"
  )
)
if not defined SKETCH (
  echo Sketch ki file is .bat par drag karke chhodo. ^(Rang ki CSV saath me bhi daal sakte ho.^)
  pause
  exit /b 1
)
for %%S in ("%SKETCH%") do (
  set "NAME=%%~nS"
  set "SDIR=%%~dpS"
)
if not defined CSV if exist "%SDIR%%NAME%.csv" set "CSV=%SDIR%%NAME%.csv"
if not defined CSV if exist "%SDIR%%NAME%_colors.csv" set "CSV=%SDIR%%NAME%_colors.csv"

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

set "OUT=%~dp0textile_project\output\paint\%NAME%"
if not exist "%OUT%" mkdir "%OUT%"
if defined REF (
  echo Rang is rangeen design se: %REF%
  if defined CSV (
    ".venv\Scripts\python.exe" -m textile paint "%SKETCH%" --out "%OUT%" --ref "%REF%" --colors "%CSV%"
  ) else (
    ".venv\Scripts\python.exe" -m textile paint "%SKETCH%" --out "%OUT%" --ref "%REF%"
  )
) else if defined CSV (
  echo Rang is CSV se: %CSV%
  ".venv\Scripts\python.exe" -m textile paint "%SKETCH%" --out "%OUT%" --colors "%CSV%"
) else (
  ".venv\Scripts\python.exe" -m textile paint "%SKETCH%" --out "%OUT%"
)
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
