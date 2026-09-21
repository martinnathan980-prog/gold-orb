#!/bin/bash
# =====================================================================
#  Ouvre Google Chrome (Mac) avec le port de debogage 9222, pour que le
#  robot se branche dessus :  navigateur: attacher: 9222
#  Interet : vous vous connectez vous-meme (SSO, MFA...) et le robot
#  travaille dans CE navigateur, avec vos sessions.
# =====================================================================
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFIL="$HOME/.autoweb-chrome"

if [ ! -x "$CHROME" ]; then
  echo "Google Chrome introuvable dans /Applications."
  echo "Ouvrez-le a la main avec :"
  echo "  \"/chemin/vers/Google Chrome\" --remote-debugging-port=9222 --user-data-dir=\"$PROFIL\""
  read -r -p "Entree pour fermer..." _
  exit 1
fi

mkdir -p "$PROFIL"
"$CHROME" --remote-debugging-port=9222 --user-data-dir="$PROFIL" --no-first-run >/dev/null 2>&1 &
echo "Chrome ouvert avec le port 9222 (profil : $PROFIL)."
echo "Connectez-vous a vos outils, puis mettez dans le scenario :"
echo "   navigateur:"
echo "     attacher: 9222"
