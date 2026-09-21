@echo off
rem ============================================================
rem  Lanceur du robot (autoweb) pour Windows.
rem  Utilisation dans l'invite de commandes, depuis ce dossier :
rem      robot demo
rem      robot base-demo
rem      robot assistant <adresse> --excel <fichier.xlsx>
rem      robot lancer <scenario.yaml>
rem ============================================================
cd /d "%~dp0"

set PY=python
where py >nul 2>nul && set PY=py -3
if exist "venv\Scripts\python.exe" set PY=venv\Scripts\python.exe

if "%~1"=="" goto aide
%PY% -m autoweb %*
exit /b %errorlevel%

:aide
echo Robot web (autoweb)
echo Dossier : %cd%
echo.
echo A taper dans cette fenetre :
echo    robot demo         verifier que tout fonctionne
echo    robot base-demo    lancer la fausse base documentaire (entrainement)
echo    robot assistant ADRESSE --excel FICHIER.xlsx --nom "ma tache"
echo    robot simuler SCENARIO.yaml
echo    robot lancer SCENARIO.yaml
echo.
%PY% -m autoweb --help
pause
