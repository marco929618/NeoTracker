@echo off
chcp 65001 > NUL
rem Creates the 'NeoTracker' icon on the Desktop (opens in its own window, no black console window).
rem Just double-click this file. The real work is done by Crea_scorciatoia.ps1.
cd /d "%~dp0"
if not exist "%~dp0neotracker.py" goto manca
if not exist "%~dp0Crea_scorciatoia.ps1" goto manca
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Crea_scorciatoia.ps1"
if errorlevel 1 goto errore
echo.
echo Done. You will find 'NeoTracker' on the Desktop: double-click it to open the program.
echo While it is open, its icon appears in the taskbar.
goto fine
:manca
echo neotracker.py or Crea_scorciatoia.ps1 is missing from this folder: %~dp0
goto fine
:errore
echo.
echo I could not create the icon (see the message above).
echo Alternatively, double-click Analizza_neo.bat: it opens NeoTracker without a black console window.
:fine
echo.
pause
