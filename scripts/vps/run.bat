@echo off
REM הרצה רציפה עם הפעלה-מחדש אוטומטית אחרי קריסה.
REM   scripts\vps\run.bat                          -> הבוט המלא (main.py)
REM   scripts\vps\run.bat scripts\listen_only.py   -> האזנה לטלגרם בלבד
setlocal
cd /d "%~dp0\..\.."

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=main.py"

set "PY="
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "pass" >nul 2>&1
  if not errorlevel 1 set "PY=.venv\Scripts\python.exe"
)
if not defined PY (
  py -c "pass" >nul 2>&1
  if not errorlevel 1 set "PY=py"
)
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.11+ or run scripts\vps\setup.ps1
  exit /b 1
)

if not exist logs mkdir logs
echo Python: %PY%
echo Target: %TARGET%
echo.

:loop
echo [%date% %time%] starting %TARGET%
"%PY%" %TARGET%
echo [%date% %time%] exited with code %errorlevel% - restarting in 10s (Ctrl+C to stop)
timeout /t 10 /nobreak >nul
goto loop
