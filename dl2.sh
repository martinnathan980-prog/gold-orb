#!/usr/bin/env bash
#
# Télécharge les bougies M1 des instruments de comparaison (marchés corrélés).
# Usage : bash dl2.sh [instrument ...]
set -euo pipefail
cd "$(dirname "$0")"

INSTRUMENTS=("$@")
if [ ${#INSTRUMENTS[@]} -eq 0 ]; then
  INSTRUMENTS=(eurusd gbpusd usdjpy deuidxeur lightcmdusd)
fi

DEBUT="${DEBUT:-2013-01-01}"
FIN="${FIN:-2026-01-01}"
mkdir -p download

for instrument in "${INSTRUMENTS[@]}"; do
  # Les noms de fichiers produits varient (Dukascopy cale la date sur le premier tick
  # disponible), on teste donc un préfixe plutôt qu'un nom exact.
  if compgen -G "download/${instrument}-m1-*" > /dev/null; then
    echo "→ ${instrument} : déjà présent, ignoré"
    continue
  fi
  echo "→ ${instrument} : téléchargement"
  npx --yes dukascopy-node \
    -i "$instrument" -from "$DEBUT" -to "$FIN" -t m1 -f csv \
    || echo "   échec sur ${instrument}, on continue"
done

echo "Terminé."
