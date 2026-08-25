#!/bin/bash
# ============================================
#  TICKS XAUUSD — tout en une commande
#  Usage :  bash ticks.sh
# ============================================
set -e
cd "$(dirname "$0")"

echo "=== 1/5  Nettoyage ==="
git reset --mixed origin/main 2>/dev/null || true
rm -f download/xauusd-tick-2025-06-01-2026-01-01.csv.gz
rm -f download/*tick*.csv download/*tick*.csv.gz
echo "    fait"

echo ""
echo "=== 2/5  Telechargement des ticks, mois par mois ==="
for m in 06 07 08 09 10 11 12; do
  echo "--- mois 2025-$m ---"
  npx --yes dukascopy-node -i xauusd -from 2025-$m-01 -to 2025-$m-28 -t tick -f csv \
    || echo "    (echec sur $m, on continue)"
done

echo ""
echo "=== 3/5  Compression ==="
gzip -9 -f download/*tick*.csv 2>/dev/null || true
ls -lhS download/ | grep tick || echo "    aucun fichier tick"

echo ""
echo "=== 4/5  Verification des tailles (limite GitHub : 100 Mo) ==="
TROP=0
for f in download/*tick*.gz; do
  [ -e "$f" ] || continue
  SZ=$(stat -c%s "$f")
  MB=$((SZ/1000000))
  if [ "$SZ" -gt 99000000 ]; then
    echo "    TROP GROS : $f  ($MB Mo)  -> supprime"
    rm -f "$f"; TROP=1
  else
    echo "    OK : $(basename $f)  ($MB Mo)"
  fi
done

echo ""
echo "=== 5/5  Envoi sur GitHub ==="
git add -A
git commit -m "ticks xauusd 2025" || echo "    rien a commiter"
git push

echo ""
echo "============================================"
echo " TERMINE."
if [ "$TROP" = "1" ]; then
  echo " Attention : certains mois etaient trop gros et ont ete retires."
fi
echo " Dis a Claude : 'ticks pousses'"
echo "============================================"
#!/bin/bash
# ============================================
#  TICKS XAUUSD — tout en une commande
#  Usage :  bash ticks.sh
# ============================================
set -e
cd "$(dirname "$0")"

echo "=== 1/5  Nettoyage ==="
git reset --mixed origin/main 2>/dev/null || true
rm -f download/xauusd-tick-2025-06-01-2026-01-01.csv.gz
rm -f download/*tick*.csv download/*tick*.csv.gz
echo "    fait"

echo ""
echo "=== 2/5  Telechargement des ticks, mois par mois ==="
for m in 06 07 08 09 10 11 12; do
  echo "--- mois 2025-$m ---"
  npx --yes dukascopy-node -i xauusd -from 2025-$m-01 -to 2025-$m-28 -t tick -f csv \
    || echo "    (echec sur $m, on continue)"
done

echo ""
echo "=== 3/5  Compression ==="
gzip -9 -f download/*tick*.csv 2>/dev/null || true
ls -lhS download/ | grep tick || echo "    aucun fichier tick"

echo ""
echo "=== 4/5  Verification des tailles (limite GitHub : 100 Mo) ==="
TROP=0
for f in download/*tick*.gz; do
  [ -e "$f" ] || continue
  SZ=$(stat -c%s "$f")
  MB=$((SZ/1000000))
  if [ "$SZ" -gt 99000000 ]; then
    echo "    TROP GROS : $f  ($MB Mo)  -> supprime"
    rm -f "$f"; TROP=1
  else
    echo "    OK : $(basename $f)  ($MB Mo)"
  fi
done

echo ""
echo "=== 5/5  Envoi sur GitHub ==="
git add -A
git commit -m "ticks xauusd 2025" || echo "    rien a commiter"
git push

echo ""
echo "============================================"
echo " TERMINE."
if [ "$TROP" = "1" ]; then
  echo " Attention : certains mois etaient trop gros et ont ete retires."
fi
echo " Dis a Claude : 'ticks pousses'"
echo "============================================"
