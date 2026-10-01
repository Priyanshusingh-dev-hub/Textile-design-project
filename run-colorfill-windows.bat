@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0colorfill"

rem colorfill: line art + coloured reference -> flat channels for the mill.
rem Every pair in colorfill\input is run: NAME_lineart.png with NAME_colored.png
rem (png, jpg or tif). Results go to colorfill\output\NAME\.

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
  echo Colorfill setup ho raha hai, ek baar hi hoga, thoda time lagega...
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
set FOUND=0
set FAILED=0
for %%F in (input\*_lineart.png input\*_lineart.jpg input\*_lineart.jpeg input\*_lineart.tif input\*_lineart.tiff) do (
  set "N=%%~nF"
  set "N=!N:_lineart=!"
  set "REF="
  for %%E in (png jpg jpeg tif tiff) do (
    if not defined REF if exist "input\!N!_colored.%%E" set "REF=input\!N!_colored.%%E"
  )
  if not defined REF (
    echo.
    echo [SKIP] %%~nxF -- iska colored reference nahi mila. Naam hona chahiye: !N!_colored.png
  ) else (
    set /a FOUND+=1
    echo.
    echo ===== !N! =====
    ".venv\Scripts\python.exe" colorfill.py --line "%%F" --ref "!REF!" --out "output\!N!" --name "!N!"
    if errorlevel 1 (
      set /a FAILED+=1
      echo [!N!] RUKA -- upar ka message dekho, aur Claude ko bhejo.
    )
  )
)

echo.
if !FOUND!==0 (
  echo colorfill\input me koi jodi nahi mili.
  echo Har design ki do files daalo: NAAM_lineart.png aur NAAM_colored.png
  start "" "%~dp0colorfill\input"
) else (
  echo !FOUND! design chale, !FAILED! ruke. Nateeje: colorfill\output
  start "" "%~dp0colorfill\output"
)
pause
endlocal
