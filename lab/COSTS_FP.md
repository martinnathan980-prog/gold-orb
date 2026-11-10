# Round 2 — cost model for the FP Markets Raw account

Values in `r2/fp_costs.json`. Source: the four web sweeps of 2026-11-10 saved in
`results/r2/_paused_state.json` (`fp_sweeps`). The account is a **Raw** account (symbols `XAUUSD.r`, …).

| Market | Modelled cost (round trip) | At price | = bp | Why this value |
|---|---|---|---|---|
| XAUUSD | 0.19 $/oz = 0.13 spread + 0.06 commission | 4,080 | 0.47 | Raw spread: 0.10 published average, 0.09–0.15 measured; commission 3 $ per side per lot (2.75 € on a EUR account) |
| US100 | 1.0 pt | 27,000 | 0.37 | 0.63 published average; independent readings 0.4 – 1.6 in US hours |
| US500 | 0.4 pt | 7,377 | 0.54 | 0.25 published and measured round the clock; other readings 0.4 – 0.6 |
| US30 | 1.8 pt | 51,286 | 0.35 | 1.43 published; measured 1.1 – 1.4; weaker sources 1.8 – 3.0 |
| GER40 | 1.6 pt | 25,820 | 0.62 | 1.54 published; measured 0.5 – 1.0 in European hours |
| BTCUSD | 22.5 $ | 76,000 | 2.96 | 22.47 published; measured 16 – 24 |
| ETHUSD | 3.0 $ | 2,300 | 13.0 | **uncertain**: 1.16 published, 2.40 and 4.32 measured by third parties |
| XAGUSD | 0.03 $ | 55.5 | 5.4 | not used by any sleeve; 0.02 + commission reported for Raw |

Indices and crypto cost the same on Raw and Standard (no commission, no separate Raw spread).

Other choices
- The cost is converted to basis points at the price where it was observed and applied to the whole
  history, with Dukascopy's intraday spread shape (wider at rollover, off-hours, news). The Raw commission
  is folded into the spread.
- Stress test = spread and slippage × 1.5 (covers the high independent readings, ETH 4.5 $ included).
- Slippage (unchanged, no broker statistics exist): stop fills 1.0 bp gold, 0.5 bp indices, 1.5 bp BTC,
  2.0 bp ETH; market fills 0.3 / 0.2 / 0.5 / 0.7 bp.
- Swaps, annual % on a 360-day basis: gold long 5.5, indices long 4.1 – 5.5, crypto long 20 and short 2;
  credits on shorts are ignored. Triple night: Wednesday for gold, Friday for indices and crypto.
- **Crypto is 24/5 at FP Markets** (closed Friday 23:55 → Monday 00:00 server time = New York + 7 h):
  weekend bars are removed from the frames; a time exit that falls in the closure is executed at the
  Friday close.
- Leverage used for margin: gold 1:500, indices 1:200, crypto 1:50.

Still to be read in the user's own MT5 (symbol "Détails" / specification)
1. Minimum volume and step of US100 / US500 (1.0, 0.1 or 0.01 lot): decides whether indices fit a 1,000 € account.
2. Live spread of ETHUSD and BTCUSD.
3. Margin rate (leverage) of XAUUSD.r and BTCUSD.
