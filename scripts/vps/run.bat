@echo off
REM הרצה רציפה עם הפעלה-מחדש אוטומטית אחרי קריסה.
REM   scripts\vps\run.bat                          -> הבוט המלא (main.py)
REM   scripts\vps\run.bat scripts\listen_only.py   -> האזנה לטלגרם בלבד
REM
REM אחרי MAXFAILS קריסות רצופות הלולאה נעצרת, כדי שתקלה קבועה (למשל MT5 שלא
REM מתחבר) לא תייצר אלפי הפעלות ביום ותחנוק את השרת.
setlocal enabledelayedexpansion
cd /d "%~dp0\..\.."

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=main.py"
set "MAXFAILS=8"

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

set /a FAILS=0
:loop
echo [%date% %time%] starting %TARGET%
"%PY%" %TARGET%
set "CODE=%errorlevel%"

if "%CODE%"=="0" (
  echo [%date% %time%] exited cleanly - stopping.
  exit /b 0
)

set /a FAILS+=1
echo [%date% %time%] exited with code %CODE% - failure !FAILS! of %MAXFAILS%

if !FAILS! GEQ %MAXFAILS% (
  echo.
  echo [STOP] %MAXFAILS% consecutive failures. Not restarting.
  echo        Check logs\ and run:  py scripts\diag_mt5.py
  exit /b 1
)

REM השהיה הולכת וגדלה: 10, 20, 30... שניות
set /a WAIT=!FAILS!*10
echo         restarting in !WAIT!s (Ctrl+C to stop)
timeout /t !WAIT! /nobreak >nul
goto loop
