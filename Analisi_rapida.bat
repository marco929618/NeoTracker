@echo off
chcp 65001 > NUL
rem Drag a photo ONTO this file to analyse it; or double-click it and pick the photo in the window.
cd /d "%~dp0"
where py > NUL 2> NUL && goto conpy
python melanoma_batch.py --foto "%~1"
goto fine
:conpy
py -3 melanoma_batch.py --foto "%~1"
:fine
echo.
pause
