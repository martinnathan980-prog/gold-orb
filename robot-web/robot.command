#!/bin/bash
# =====================================================================
#  Lanceur du robot (autoweb) pour Mac et Linux.
#  Sans rien taper d'autre, il ouvre le menu :
#      ./robot.command
#  Ou directement une commande :
#      ./robot.command enregistrer https://mon-outil --excel suivi.xlsx --nom "ma tache"
#      ./robot.command lancer ma_tache.yaml --limite 1
#      ./robot.command base-demo
# =====================================================================
cd "$(dirname "$0")" || exit 1

if [ -x "venv/bin/python" ]; then
  PY="venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

exec "$PY" -m autoweb "$@"
