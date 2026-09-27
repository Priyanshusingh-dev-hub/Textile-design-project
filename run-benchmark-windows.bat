@echo off
rem LoomLab benchmark: drag a folder of designs onto this file. Every design
rem goes through auto mode and a report opens in the browser. An operator's
rem own separation saved as NAME.operator.png beside NAME.png is compared too.
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Designs wala folder is file par kheench kar chhodo ^(drag and drop^).
  pause
  exit /b 1
)
if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Pehle run-windows.bat ek baar chalao, woh setup karta hai.
  pause
  exit /b 1
)
set /p WIDTH=Print kitne inch chauda? (khaali = file ka apna size): 
set /p METERS=Quote kitne meter ka? (khaali = quote nahi): 
set ARGS=
if not "%WIDTH%"=="" set ARGS=%ARGS% --width-in %WIDTH%
if not "%METERS%"=="" set ARGS=%ARGS% --meters %METERS%
cd backend
".venv\Scripts\python.exe" -m app.benchmark "%~1" %ARGS% --open
pause
endlocal
