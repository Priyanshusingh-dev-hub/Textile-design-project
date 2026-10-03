@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0textile_project"

rem textile number: a COLOURED design, every patch of one colour gets a number.
rem Drag the coloured design onto this file. Use it to plan a sketch: the same parts,
rem the same numbers. Results: textile_project\output\number\<design name>\
rem   NAME_numbers.png  the design with every patch outlined and numbered
rem   NAME_colors.csv   every number's colour (textile paint reads this CSV)
rem   NAME_flat.png     the design in its flat inks
rem   NAME_sketch_seal0.png    the colours taken away: only the lines, the same parts
rem   NAME_sketch_numbers.png  that sketch with the same numbers
rem   (drag NAME_sketch_seal0.png + NAME_colors.csv on run-paint-windows.bat: the design comes back)

if "%~1"=="" (
  echo Rangeen design ki file is .bat par drag karke chhodo.
  pause
  exit /b 1
)
set "NAME=%~n1"

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

set "OUT=%~dp0textile_project\output\number\%NAME%"
if not exist "%OUT%" mkdir "%OUT%"
".venv\Scripts\python.exe" -m textile number "%~f1" --out "%OUT%"
if errorlevel 1 (
  echo.
  echo Ruk gaya -- upar ka STOP wala message padho, ya Claude ko bhejo.
  pause
  exit /b 1
)
for %%F in ("%OUT%\*_sketch_numbers.png") do start "" "%%F"
start "" "%OUT%"
pause
endlocal
