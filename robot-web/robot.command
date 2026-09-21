#!/bin/bash
# =====================================================================
#  Lanceur du robot (autoweb) pour Mac et Linux.
#  Utilisation dans le Terminal, depuis le dossier robot-web :
#      ./robot.command demo
#      ./robot.command base-demo
#      ./robot.command assistant <adresse> --excel <fichier.xlsx>
#      ./robot.command lancer <scenario.yaml>
#  Un double-clic (sans rien taper) affiche la liste des commandes.
# =====================================================================
cd "$(dirname "$0")" || exit 1

if [ -x "venv/bin/python" ]; then
  PY="venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

if [ $# -eq 0 ]; then
  echo "Robot web (autoweb)"
  echo "Dossier : $(pwd)"
  echo
  echo "A taper dans le Terminal, depuis ce dossier :"
  echo "   ./robot.command demo         verifier que tout fonctionne"
  echo "   ./robot.command base-demo    lancer la fausse base documentaire (entrainement)"
  echo "   ./robot.command assistant ADRESSE --excel FICHIER.xlsx --nom \"ma tache\""
  echo "   ./robot.command simuler SCENARIO.yaml"
  echo "   ./robot.command lancer SCENARIO.yaml"
  echo
  "$PY" -m autoweb --help
  echo
  read -r -p "Appuyez sur Entree pour fermer cette fenetre..." _
  exit 0
fi

exec "$PY" -m autoweb "$@"
