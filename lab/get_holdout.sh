#!/bin/bash
# Download the 2026 HOLDOUT data (M1 bid+ask XAUUSD, and bid for the other markets).
# PROTOCOL: run ONCE, at the very end, after finalists are frozen. Never tune on it.
set -e
cd "$(dirname "$0")"
mkdir -p holdout_raw && cd holdout_raw && RFLAGS="-r 3 -re"
TO=${1:-$(date -u +%Y-%m-%d)}
for p in bid ask; do npx --yes dukascopy-node -i xauusd -from 2026-01-01 -to "$TO" -t m1 -p $p -f csv $RFLAGS; done
# (other markets not needed: all holdout candidates trade XAUUSD)
# for i in eurusd gbpusd usdjpy deuidxeur lightcmdusd; do npx --yes dukascopy-node -i $i -from 2026-01-01 -to "$TO" -t m1 -f csv $RFLAGS; done
ls -lh download
