for i in eurusd gbpusd usdjpy deuidxeur lightcmdusd; do npx dukascopy-node -i $i -from 2013-01-01 -to 2026-01-01 -t m1 -f csv; done
