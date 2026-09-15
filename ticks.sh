#!/usr/bin/env bash
#
# Télécharge les ticks XAUUSD mois par mois, les compresse et vérifie
# qu'ils passent la limite de 100 Mo par fichier de GitHub.
#
# Usage :
#   bash ticks.sh                      # 2025-06 à 2025-12
#   bash ticks.sh 2025-01 2025-05      # plage explicite
#   POUSSER=1 bash ticks.sh            # commit + push à la fin
#
# Le script ne commite rien par défaut : il ne touche à l'historique git
# que si POUSSER=1 est demandé explicitement.
set -euo pipefail
cd "$(dirname "$0")"

MOIS_DEBUT="${1:-2025-06}"
MOIS_FIN="${2:-2025-12}"
LIMITE_OCTETS=99000000
mkdir -p download download/trop-gros

# --- 1/4  Liste des mois à traiter ---------------------------------------
mois_courant="$MOIS_DEBUT"
mois=()
while [[ "$mois_courant" < "$MOIS_FIN" || "$mois_courant" == "$MOIS_FIN" ]]; do
  mois+=("$mois_courant")
  mois_courant=$(date -u -d "${mois_courant}-01 +1 month" +%Y-%m)
done
echo "=== 1/4  ${#mois[@]} mois à traiter : ${mois[*]} ==="

# --- 2/4  Téléchargement --------------------------------------------------
echo ""
echo "=== 2/4  Téléchargement des ticks ==="
for m in "${mois[@]}"; do
  # Borne de fin exclusive = premier jour du mois suivant.
  # L'ancienne version s'arrêtait au 28 et perdait les 2 à 3 derniers jours de chaque mois.
  debut="${m}-01"
  fin=$(date -u -d "${debut} +1 month" +%Y-%m-%d)

  if compgen -G "download/xauusd-tick-${debut}-*" > /dev/null; then
    # Les fichiers produits par l'ancienne version s'arrêtaient au 28 du mois :
    # on les signale, ils sont incomplets.
    if compgen -G "download/xauusd-tick-${debut}-${m}-28.*" > /dev/null; then
      echo "--- ${m} : fichier partiel (arrêté au 28) — supprimez-le pour retélécharger le mois complet"
    else
      echo "--- ${m} : déjà présent, ignoré"
    fi
    continue
  fi

  echo "--- ${m} : ${debut} → ${fin}"
  npx --yes dukascopy-node -i xauusd -from "$debut" -to "$fin" -t tick -f csv \
    || echo "    échec sur ${m}, on continue"
done

# --- 3/4  Compression -----------------------------------------------------
echo ""
echo "=== 3/4  Compression ==="
if compgen -G "download/*tick*.csv" > /dev/null; then
  gzip -9 -f download/*tick*.csv
  echo "    fait"
else
  echo "    rien à compresser"
fi

# --- 4/4  Contrôle de taille ---------------------------------------------
echo ""
echo "=== 4/4  Vérification des tailles (limite GitHub : 100 Mo) ==="
trop_gros=0
for f in download/*tick*.gz; do
  [ -e "$f" ] || continue
  taille=$(wc -c < "$f")
  mo=$((taille / 1000000))
  if [ "$taille" -gt "$LIMITE_OCTETS" ]; then
    # On déplace au lieu de supprimer : perdre des données téléchargées
    # pendant des heures pour une limite d'hébergement serait absurde.
    echo "    TROP GROS : $(basename "$f") (${mo} Mo) → download/trop-gros/"
    mv "$f" download/trop-gros/
    trop_gros=1
  else
    echo "    OK : $(basename "$f") (${mo} Mo)"
  fi
done

# --- Envoi optionnel sur GitHub ------------------------------------------
if [ "${POUSSER:-0}" = "1" ]; then
  echo ""
  echo "=== Envoi sur GitHub ==="
  branche=$(git rev-parse --abbrev-ref HEAD)
  git add -A download
  git commit -m "ticks xauusd ${MOIS_DEBUT} → ${MOIS_FIN}" || echo "    rien à commiter"
  git push -u origin "$branche"
fi

echo ""
echo "============================================"
echo " Terminé."
if [ "$trop_gros" = "1" ]; then
  echo " Attention : des fichiers dépassent 100 Mo, ils sont dans download/trop-gros/"
  echo " (à découper, ou à publier via git-lfs / une release GitHub)."
fi
[ "${POUSSER:-0}" = "1" ] || echo " Rien n'a été commité. Relancer avec POUSSER=1 pour publier."
echo "============================================"
