@echo off
rem ============================================================
rem  Installation d'autoweb sur un poste Windows (sans droits admin)
rem  Double-cliquez sur ce fichier ou lancez-le depuis une invite.
rem ============================================================
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

echo [1/3] Version de Python :
%PY% --version || (echo Python introuvable. Installez Python 3.9+ ou ajoutez-le au PATH. & pause & exit /b 1)

echo.
echo [2/3] Installation des bibliotheques (pip)...
%PY% -m pip install --user --upgrade -r requirements.txt
if errorlevel 1 (
  echo.
  echo Echec de pip. Derriere un proxy d'entreprise, essayez :
  echo    set HTTPS_PROXY=http://proxy.entreprise:8080
  echo    %PY% -m pip install --user --proxy %%HTTPS_PROXY%% --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
  pause
  exit /b 1
)

echo.
echo [3/3] Verification avec le formulaire de demonstration (Edge/Chrome installe)...
%PY% -m autoweb demo --sans-pause
echo.
echo Si le navigateur n'a pas pu etre lance, executez une fois :
echo    %PY% -m playwright install chromium
echo puis relancez :  %PY% -m autoweb demo
pause
