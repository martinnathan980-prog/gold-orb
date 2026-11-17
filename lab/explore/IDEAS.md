# Idea queue of the open search

Status: `ouverte` (not tried), `en cours`, `fermee` (tried, see LEDGER.md), `trouvee`. A run takes the idea marked
`en cours`, else the first `ouverte`, or adds a better one of its own here first (with why it is unusual and the
mechanism). Numbers are never reused. Each idea needs at least 4 years of in-sample history (before 2022).

| N | Idea | Data | Sketch of the rule | Why it may hold, why it is unusual | Status |
|---|---|---|---|---|---|
| 001 | Crypto weekend move, then Monday at FP | Binance 1h klines BTC, ETH (2017-2021) | FP's crypto CFDs are shut from Friday 23:55 to Sunday 24:00 server while crypto trades. Does the weekend move continue or revert during Monday's CFD session? Enter at the CFD's reopening, exit the same day | Specific to a broker closing a 24/7 market; retail flow reacts at the reopening | fermee |
| 002 | World news tone shock | GDELT 2.0 events (2015-2021), Dukascopy H1 | Daily average tone of world events: a shock (z-score of the day against 60 days) predicts risk-off for 1-5 days (long gold or JPY, short US500 or GER40) | Machine-read news tone, rarely used by retail rules | en cours |
| 003 | Conflict event spikes | GDELT 2.0 events, CAMEO root codes 18-20 (2015-2021) | A spike in the count of violent events predicts gold, oil and USDJPY over 1-5 days | Geopolitical risk measured from raw event counts | ouverte |
| 004 | Policy uncertainty jumps | FRED USEPUINDXD (daily, since 1985) | A jump in the daily economic policy uncertainty index predicts next-week index and gold moves | Text-based uncertainty index, slow and seldom traded | ouverte |
| 005 | Credit leads equity | FRED BAMLH0A0HYM2 (high-yield spread, daily) | A widening of the high-yield spread not yet matched by US500 predicts US500's next days | Bond market information reaching equity CFDs late | en cours (2026-11-17 22:45 UTC) |
| 006 | Gold against real yields | FRED DFII10 (10-year real yield, daily since 2003), Dukascopy XAUUSD | Residual of gold's daily move against real yields and the dollar: fade the residual over days | Macro-factor residual, not a chart pattern | ouverte |
| 007 | Abnormal hourly volume | Dukascopy H1 volume (2013-2021): gold, US indices, FX majors | An hour whose volume is far above its usual level for that hour of the week: does its direction continue for the next hours? | Volume only, against its own hour-of-week profile | ouverte |
| 008 | Spread stress | Dukascopy H1 bid and ask (spread per hour) | Hours with abnormally wide spreads (liquidity stress) predict a reversal once spreads normalise | The broker-side liquidity signal itself as data | ouverte |
| 009 | Bitcoin mining difficulty | blockchain.info charts (hash rate, difficulty; check access) | Large difficulty adjustments or hash-rate drops predict BTC returns over the next days | On-chain supply side, outside price data | ouverte |
| 010 | Stablecoin issuance | Coin Metrics community API (USDT supply; check access) | Fast growth of stablecoin supply predicts BTC and ETH over the next week | Money flowing into crypto before it buys | ouverte |
| 011 | BTC/ETH ratio stretch | Binance 1h or 4h klines (2017-2021) | Fade large deviations of the ETH/BTC ratio from its recent mean, hedged pair | Relative value inside crypto, not direction | ouverte |
| 012 | Fed balance sheet weeks | FRED WALCL (weekly since 2002) | The weekly change of the Fed's balance sheet predicts the next week of US500, gold and the dollar | Liquidity flow measured, not guessed | ouverte |
| 013 | US Treasury auction tails | TreasuryDirect auction results (check access) | A weak auction (high tail) predicts USDJPY and US500 over the next hours or days | Rare data source for CFD traders | ouverte |
| 014 | Macro-factor residual basket | Dukascopy H1 or daily FX, gold, oil, indices | Each market's daily move explained by the dollar, oil and rates; trade the largest residuals back, as one basket | Statistical arbitrage on macro factors, not price patterns | ouverte |
