@echo off
rem ============================================================
rem  Ouvre Google Chrome avec le port de debogage 9222, pour que le
rem  robot se branche dessus (navigateur.attacher: 9222).
rem  Interet : vous vous connectez vous-meme (SSO, carte, MFA...) et
rem  le robot travaille dans CE navigateur, avec vos sessions.
rem ============================================================
set PROFIL=%LOCALAPPDATA%\autoweb-chrome
if not exist "%PROFIL%" mkdir "%PROFIL%"

set CHROME="%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% (
  echo Chrome introuvable. Ouvrez votre navigateur a la main avec :
  echo    chrome.exe --remote-debugging-port=9222 --user-data-dir="%PROFIL%"
  pause
  exit /b 1
)

start "" %CHROME% --remote-debugging-port=9222 --user-data-dir="%PROFIL%" --no-first-run
echo Chrome ouvert avec le port 9222 (profil : %PROFIL%).
echo Connectez-vous a vos outils, puis lancez le robot avec un scenario contenant :
echo    navigateur:
echo      attacher: 9222
