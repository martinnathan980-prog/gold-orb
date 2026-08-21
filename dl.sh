for y in {2013..2025}; do
for p in bid ask; do
npx dukascopy-node -i xauusd -from $y-01-01 -to $((y+1))-01-01 -t m1 -p $p -f csv
done
done
