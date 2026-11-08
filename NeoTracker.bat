@echo off
chcp 65001 > NUL
title NeoTracker - finestra di diagnosi
rem Versione "con la finestra nera" di NeoTracker: l'app si apre comunque nella sua finestra,
rem ma qui sotto puoi leggere i messaggi del programma se qualcosa non funziona.
rem Per l'uso di tutti i giorni usa l'icona sul Desktop (senza finestra nera).
cd /d "%~dp0"
where py > NUL 2> NUL && goto conpy
where python > NUL 2> NUL && goto conpython
echo Python non e' installato (o non e' nel PATH).
echo Installalo da https://www.python.org/downloads/ e spunta "Add python.exe to PATH".
goto fine
:conpy
py -3 neotracker.py
goto fine
:conpython
python neotracker.py
:fine
echo.
echo NeoTracker e' chiuso. Premi un tasto per chiudere questa finestra.
pause > NUL
