@echo off
chcp 65001 > NUL
rem Crea sul Desktop l'icona 'NeoTracker' (si apre nella sua finestra, senza finestra nera).
rem Basta un doppio clic su questo file. Il lavoro vero lo fa Crea_scorciatoia.ps1.
cd /d "%~dp0"
if not exist "%~dp0neotracker.py" goto manca
if not exist "%~dp0Crea_scorciatoia.ps1" goto manca
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Crea_scorciatoia.ps1"
if errorlevel 1 goto errore
echo.
echo Fatto. Trovi 'NeoTracker' sul Desktop: doppio clic per aprire il programma.
echo Mentre e' aperto, la sua icona compare nella barra delle applicazioni.
goto fine
:manca
echo Mancano neotracker.py o Crea_scorciatoia.ps1 in questa cartella: %~dp0
goto fine
:errore
echo.
echo Non sono riuscito a creare l'icona (vedi il messaggio sopra).
echo In alternativa fai doppio clic su Analizza_neo.bat: apre NeoTracker senza finestra nera.
:fine
echo.
pause
