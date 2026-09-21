@echo off
rem ============================================================
rem  Lanceur du robot (autoweb) pour Windows.
rem  Sans rien taper d'autre, il ouvre le menu :
rem      robot
rem  Ou directement une commande :
rem      robot enregistrer https://mon-outil --excel suivi.xlsx --nom "ma tache"
rem      robot lancer ma_tache.yaml --limite 1
rem      robot base-demo
rem ============================================================
cd /d "%~dp0"

set PY=python
where py >nul 2>nul && set PY=py -3
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe

%PY% -m autoweb %*
exit /b %errorlevel%
