@echo off
chcp 65001 > NUL
title NeoTracker - diagnostic window
rem "Console window" version of NeoTracker: the app still opens in its own window,
rem but here you can read the program messages if something does not work.
rem For everyday use, use the Desktop icon (no black console window).
cd /d "%~dp0"
where py > NUL 2> NUL && goto conpy
where python > NUL 2> NUL && goto conpython
echo Python is not installed (or is not on the PATH).
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
goto fine
:conpy
py -3 neotracker.py
goto fine
:conpython
python neotracker.py
:fine
echo.
echo NeoTracker is closed. Press any key to close this window.
pause > NUL
