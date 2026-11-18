# Direction 3 of the open search (lead, 2026-11-18, written after the batch of that day and before any run below)

## What the batch of 18 November showed
Eight ideas, none passes (ledger lines 051 to 058). Slow trends give nothing before costs (055, 058). Buying before
results is the shares' own rise (053); following the move during the results day loses even gross (054). Two things
did show a gross edge for the first time in this search:
- **Oil** (056, 057): PF gross 1.40 and 1.30, but all of it on the short side in three crash years, t 1.4 and 0.1 net.
- **Earnings drift** (052): PF gross 1.31 on 350 trades, eaten by about 30 bp of costs. Read by size of the
  reaction (a look at the result, AFTER the verdict, by the lead; `lab/explore/ideas/052_earnings_drift`, trades
  re-read with the move of each event): 3-5 %: -5 bp gross a trade (164 trades); 5-8 %: +12 bp (106); 8-12 %:
  +118 bp (55); above 12 %: +167 bp (25). At 8 % or more: 80 trades, +133 bp gross (t 2.5), +101 bp net (t 1.9), PF
  net 1.79, every year from 2017 to 2021 positive. The larger the shock, the stronger the drift: the textbook shape
  of post-earnings drift.

That last reading is a bucket chosen after seeing results on 40 shares: it is a hypothesis, not a finding, and 80
events cannot carry the bars. **The honest test is on OTHER shares**: the same rule, declared before any result,
on several hundred US shares that were not in the 40. If the drift after large shocks is real it must show there.

## The test bed: a broad set of US shares on daily bars
- **Universe**: the companies of the S&P 500 list (Wikipedia's table: ticker, SEC number, sector, date added), minus
  the lab's 40 shares. A share enters the universe on the later of 2017-01-01 and the date it joined the index (no
  look-ahead at inclusion). Shares that left the index before the list was read are missing (survivors only): said
  with every result; the random-entry null on the same share and side is what guards against the survivors' rise.
- **Prices**: daily bars from Yahoo's chart API, 2016-2021 (the reply's metadata block carries today's price: it is
  never parsed, printed or stored). Daily, because no hourly history of these shares is reachable; so signals are
  read at the session's close and orders go in at the next session's open.
- **Events**: every 8-K of each company from SEC EDGAR with its items and acceptance time (the method of
  `scout/earnings_edgar.py`, verified on the 40): item 2.02 marks results; the other items mark other news.
- **Costs, PROVISIONAL and deliberately heavy**: spread 12 bp of price, 25 bp for an order at the session's open;
  commission max(0.03 USD a share, 2 USD an order) at the charter's stake; slippage 1 bp (2 on a stop); swaps 7 %
  long and 3 % short a year; dividends (a short pays, a long is credited 70 %).
- **Kit v2.2**: generic US shares on daily bars (one bar a session), with the tests and an adversarial review, as for
  every kit change.

## Charter amendment (2026-11-18, before any run on this universe): baskets of many markets
With several hundred markets and two or three trades each, "65 % of markets positive" and "no market above 25 % of
the profit" say nothing (a market with two trades is positive or negative by chance). For a basket of MORE THAN 40
markets the two basket bars are read on GROUPS of markets fixed in the declaration before any result (at least 8
groups: here the 11 sectors of the list): at least 65 % of the groups positive, no group above 25 % of the profit.
Every other bar is unchanged.

## Ideas (each row is a full brief for one run; nothing here was tested on this universe)

| N | Idea | Family | Data | Sketch of the rule | Why it may hold | Power |
|---|---|---|---|---|---|---|
| 059 | Large earnings shocks: follow a results-day move of 8 % or more for five sessions, on the broad universe | Earnings (shares, broad) | Daily bars of the broad universe (2017-2021, kit v2.2, PROVISIONAL costs); the 8-K calendar from EDGAR (results = item 2.02, the rows known to be late dropped) | Reaction session R = the first regular session that starts after the acceptance time of the results 8-K. Move = close of R against the close of the session before. If the move is at or beyond +/-8 %: enter in its direction at the open of session R+1, exit at the open five sessions later, stop 1.5 x D20, one position per share. Basket of the whole universe, groups = sectors. The 40 shares of idea 052 are NOT in it. Neighbours: thresholds 6 % and 10 %, holds of 3 and 4 sessions, stops 1 and 2 x D20 | Post-earnings-announcement drift, strongest after the largest surprises (Bernard and Thomas 1989; the announcement return as the surprise: Brandt, Kishore, Santa-Clara and Venkatachalam 2008). On the lab's 40 shares the drift was nil below 5 % and +133 bp gross at 8 % or more: a hypothesis from one sample, tested here on another | Several hundred shares x 20 quarters, about one results day in ten beyond 8 %: count first (expected 400 to 900) |
| 060 | Large earnings shocks, held for weeks | Earnings (shares, broad), slow track | Same | SLOW TRACK (declared.json "track": "slow"). Same events and entry as 059; exit at the open 40 sessions later, stop 3 x D20 | The classic drift runs for about sixty trading days; if five sessions catch a part, forty should catch more, at the price of swaps and of the next results (about one hold in two crosses into the next quarter's window: said, counted) | Same events as 059 |
| 061 | Large shocks on other news: follow a move of 8 % or more on a day the company filed an 8-K that is not results | News (shares, broad) | Same; every 8-K with its items | Event = an 8-K WITHOUT item 2.02 accepted between the previous session's close and the session's close, on a day that is not a results reaction session (nor the session after one). Move = close against the previous close on that session. If at or beyond +/-8 %: same entry, exit and stop as 059 | Prices drift after news and revert after moves without news (Chan 2003; Tetlock 2010): a large move confirmed by a filing is information being absorbed. Fewer events than results days, and of many kinds (deals, departures, guidance, legal) | Count first; close as insufficient under 250 |
| 062 | Large moves without news: fade a move of 8 % or more on a day with no filing | News (shares, broad) | Same | A session whose close is at or beyond +/-8 % from the previous close, with NO 8-K of the company accepted from two sessions before to the session's close, and no results reaction session within two sessions. Enter AGAINST the move at the open of the next session, exit at the open five sessions later, stop 1.5 x D20 | The other half of the same literature: large moves without public news tend to revert (liquidity shocks, overreaction). Market-wide crash days produce many such signals at once (March 2020): the same-day null and the daily-sum t are what judge it | Count first |
