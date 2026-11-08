@echo off
rem Doppio clic: apre NeoTracker nella sua finestra (senza finestra nera).
rem Trascinando una foto sopra questo file si ottiene invece l'analisi rapida di quella foto.
if not "%~1"=="" goto rapida
cd /d "%~dp0"
where pyw > NUL 2> NUL && goto conpyw
where pythonw > NUL 2> NUL && goto conpythonw
rem Nessun interprete "senza finestra nera" trovato: uso quello normale.
call "%~dp0NeoTracker.bat"
goto :eof
:conpyw
start "" pyw -3 "%~dp0neotracker.py"
goto :eof
:conpythonw
start "" pythonw "%~dp0neotracker.py"
goto :eof
:rapida
call "%~dp0Analisi_rapida.bat" "%~1"
