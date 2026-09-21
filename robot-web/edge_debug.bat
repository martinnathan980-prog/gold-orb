@echo off
rem ============================================================
rem  Ouvre Microsoft Edge avec le port de debogage 9222, pour que le
rem  robot se branche dessus (navigateur.attacher: 9222).
rem  Interet : vous vous connectez vous-meme (SSO, carte, MFA...) et
rem  le robot travaille dans CE navigateur, avec vos sessions.
rem ============================================================
set PROFIL=%LOCALAPPDATA%\autoweb-edge
if not exist "%PROFIL%" mkdir "%PROFIL%"

set EDGE="%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist %EDGE% set EDGE="%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist %EDGE% (
  echo Edge introuvable. Ouvrez votre navigateur a la main avec :
  echo    msedge.exe --remote-debugging-port=9222 --user-data-dir="%PROFIL%"
  pause
  exit /b 1
)

start "" %EDGE% --remote-debugging-port=9222 --user-data-dir="%PROFIL%" --no-first-run
echo Edge ouvert avec le port 9222 (profil : %PROFIL%).
echo Connectez-vous a vos outils, puis lancez le robot avec un scenario contenant :
echo    navigateur:
echo      attacher: 9222
