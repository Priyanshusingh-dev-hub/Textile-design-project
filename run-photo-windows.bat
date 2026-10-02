@echo off
rem Photo -> mill design, one way for every picture: drag a folder of pictures
rem onto this file. NAME_lineart.png + NAME_ref.png (or _colored) are a pair (the
rem fill judge picks the best way); any other picture goes through Reduce alone.
rem Each gets clean edges and the mill package at 3535 px / 300 DPI in
rem <folder>\output\NAME\ (final .tif for the mill, .png overlapped, compare.png).
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Pictures wala folder is file par kheench kar chhodo ^(drag and drop^).
  pause
  exit /b 1
)
if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] Pehle run-windows.bat ek baar chalao, woh setup karta hai.
  pause
  exit /b 1
)
cd backend
".venv\Scripts\python.exe" -m app.photo_batch "%~1" --open
pause
endlocal
