#!/usr/bin/env bash
#
# Télécharge les bougies M1 de XAUUSD (bid et ask), année par année.
# Usage : bash dl.sh [année_début] [année_fin]
set -euo pipefail
cd "$(dirname "$0")"

ANNEE_DEBUT="${1:-2013}"
ANNEE_FIN="${2:-2025}"
mkdir -p download

for annee in $(seq "$ANNEE_DEBUT" "$ANNEE_FIN"); do
  for cote in bid ask; do
    # Le fichier peut être déjà présent, compressé ou non : on ne retélécharge pas.
    motif="download/xauusd-m1-${cote}-${annee}-01-01-$((annee + 1))-01-01.csv"
    if [ -f "$motif" ] || [ -f "$motif.gz" ]; then
      echo "→ ${annee} ${cote} : déjà présent, ignoré"
      continue
    fi
    echo "→ ${annee} ${cote} : téléchargement"
    npx --yes dukascopy-node \
      -i xauusd -from "${annee}-01-01" -to "$((annee + 1))-01-01" -t m1 -p "$cote" -f csv \
      || echo "   échec sur ${annee} ${cote}, on continue"
  done
done

echo "Terminé."
