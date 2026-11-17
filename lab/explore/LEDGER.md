# Ledger of the open search (one line per idea; the running total of configurations matters)

Configurations tested by the lab before this search: about 2,500 (round 1 321, round 2 about 560, pivots and Bollinger 76,
micro 8, language-model tests 2, round 3 tracks, round 4 55, round 5, round 6 91; see lab/PROTOCOL*.md). Use the
running total below for the deflated Sharpe ratio.

Running total of configurations (before this search + this search): **2500**

| N | Date | Idea | Markets | Data (in-sample years) | Configs | Verdict | Key figures (main configuration) |
|---|---|---|---|---|---|---|---|
| 001 | 2026-11-17 | Crypto weekend move, then Monday at FP | BTCUSD, ETHUSD | Binance 1h from 2017-08 (4.4 years) | 0 | fermee : donnees insuffisantes (structurellement) | At most about 228 Mondays per market before 2022, below n >= 250; a basket of two markets cannot meet 'no market above 25 % of the profit'. No test run. (Concluded by the runs of 16-17 November, whose work could not be pushed: written here by the lead.) |
| 002 | 2026-11-17 | World news tone shock (GDELT) | XAUUSD, USDJPY, US500, GER40 (basket) | GDELT 1.0 daily events 2013-04..2021-12 (8.75 years, 3,193 days, 4 missing); Dukascopy H1 | 8 declared, 0 run | en cours | Declared and pushed (sha 20a87637...). GDELT daily tone built in the cache (~/explore_data/gdelt, 151 main signals z<=-2 on 60 days). Dukascopy throttled this run (16 s per request, then repeated failures): only 50 of 432 monthly H1 files fetched, so no result yet. Next run: re-run fetch_gdelt.py if the cache is gone (about 10 min with 8 processes), fetch the four Dukascopy symbols sequentially and slowly, then run.py (needs scipy, pyarrow). |
