@echo off
chcp 65001 > NUL
rem Trascina una foto SOPRA questo file per analizzarla; oppure fai doppio clic e scegli la foto nella finestra.
cd /d "%~dp0"
where py > NUL 2> NUL && goto conpy
python melanoma_batch.py --foto "%~1"
goto fine
:conpy
py -3 melanoma_batch.py --foto "%~1"
:fine
echo.
pause
