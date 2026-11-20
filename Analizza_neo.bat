@echo off
rem Double-click: opens NeoTracker in its own window (no black console window).
rem Dragging a photo onto this file runs the quick analysis of that photo instead.
if not "%~1"=="" goto rapida
cd /d "%~dp0"
where pyw > NUL 2> NUL && goto conpyw
where pythonw > NUL 2> NUL && goto conpythonw
rem No "windowless" interpreter found: use the normal one.
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
