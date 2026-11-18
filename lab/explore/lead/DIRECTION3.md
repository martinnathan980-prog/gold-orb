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

## What the data preparation settled (2026-11-18, after an adversarial review of the data; still before any run)
The data exist and were attacked by an independent verifier, then repaired (`scout/sources.md` section 31):
382 shares (the S&P 500 list minus the lab's 40 and minus the 79 that joined in 2022 or later; 11 sectors), daily
bars 2016-2021 for all of them, and 32,221 filings of form 8-K with their acceptance times. Five things are fixed
here, in the light of counts of SIGNALS only (no return after a signal was computed):
1. **The event session** of a filing is the first session that CLOSES after its acceptance time (`event_session`):
   a filing made before the open or during the session belongs to that session, a filing after the close to the
   next one. The move is read at that session's close, when both the filing and the price are public. (The earlier
   'reaction session' put filings made during the session a day late: prices showed it on 487 results rows.)
2. **Moves are read net of the market**: abnormal move = the share's close-to-close return minus the MEDIAN return of
   the universe's shares that session. Without it the March 2020 crash floods every count.
3. **Idea 061 is closed without a run** (power): 8-K days that are not results rarely carry a large move in large
   companies: 130 events at 8 % in five years, 88 of them in 2020; 236 at 5 % outside turmoil. The filing is also
   often made days after the news. Not testable on this universe.
4. **Idea 062 needs a calm market**: at 8 % it has 1,021 signals, 839 of them in 2020. It is declared on sessions
   where the universe's median absolute move is under 2 % (105 of 1,511 sessions are excluded, 63 of them in 2020),
   at 6 %: 935 signals on 442 days (75 / 98 / 104 / 379 / 279 by year).
5. **Survivors only, said plainly**: 183 companies that were in the index during 2017-2021 are missing because they
   left it since (a quarter of the 2017 index). Companies whose falls went on were removed; the short side after bad
   shocks is therefore judged on a sample that lacks its best cases, and a share's rise over the years is not what a
   five-session trade earns. Every result gives the long and the short side apart, and says this.
Counts of signals for idea 059 (results days, abnormal move at or beyond 8 %): 532 on 332 days; by year 80, 128, 130,
99, 95; 255 up, 277 down. At 6 %: 1,069; at 10 %: 269.

## Kit v2.2 and the last design choices (2026-11-18 afternoon, still before any run on the universe)
Kit v2.2 (generic US shares on daily bars, group bars, session exits) was built, attacked by an independent
verifier and repaired (195 self-tests). What it settles for the ideas below:
- **Costs, PROVISIONAL and heavy:** an order at the session's open pays a 56 bp spread (the review raised the lead's
  25 bp: the lab's 40 shares cost 37 bp at the 09:30 first minute in the median, 47 bp at the 75th percentile, and
  these shares are smaller), an order at a close 12 bp; commission max(0.03 USD a share, 2 USD an order), computed on
  Yahoo's price levels, which are too low for shares that split after 2021 (pessimistic for them);
  slippage, swaps, dividends as for the 40. A robot that waits a few minutes after the open would pay much less than
  56 bp: each run therefore also REPORTS (never judges) the main configuration with the open priced like a close
  (12 bp) and with the minimum commission alone.
- **Exit at a close, not at an open** (decided on costs, before any result): the trades leave at the close of the
  fifth session of the hold. An exit at an open would pay the 56 bp a second time.
- **What the 40 shares say about the timing** (the exploration sample, gross, no stop; `ideas/052_earnings_drift`
  re-read by the lead): after a results-day move of 8 % or more, the price gives back about 30 bp during the first
  night (t -1.8) and then drifts +128 bp from the next open to the close five sessions after the event (83 events,
  t 2.2; +112 bp on 144 events at 6 %). The daily-bar rule (signal at the close, entry at the next open) is
  therefore the same hypothesis, not a weaker one.
- **Moves** are read with `data.session_moves` (`ret_total`: the dividend of an ex-date is added back), net of the
  median `ret_total` of the universe's shares that session; a session flagged `action` (a large dividend, a split or
  spin-off record) gives no signal.

## Ideas (each row is a full brief for one run; nothing here was tested on this universe)

| N | Idea | Family | Data | Sketch of the rule | Why it may hold | Power |
|---|---|---|---|---|---|---|
| 059 | Large earnings shocks: follow a results-day move of 8 % or more for five sessions, on the broad universe | Earnings (shares, broad) | Daily bars of the broad universe (2017-2021, kit v2.2: `data.load_bars(key)` for the keys of `kit/universe_us.csv`, PROVISIONAL costs); the 8-K calendar from EDGAR: `scout/events_edgar.py`, `idea_sessions('059')` (results rows by event session, the rows known to be late dropped); `scout/sources.md` section 31 | Event session S = the first session that closes after the results 8-K was accepted (the calendar's event_session). Abnormal move = the share's `ret_total` on S (`data.session_moves`) minus the median `ret_total` of the universe's shares on S; no signal on a session flagged `action`. If it is at or beyond +/-8 %: enter in its direction at the open of the next session, exit at the CLOSE of the fifth session of the hold (the entry session is the first), stop 1.5 x D20, one position per share. Basket of the whole universe, groups = the 11 sectors (declared.json "groups": "sector"). The 40 shares of idea 052 are NOT in it. Neighbours: thresholds 6 % and 10 %; exit at the close of the third and of the fourth session; exit at the open of the sixth session; stops 1 and 2 x D20. Report: the long and the short side apart, each year, each sector; `checks.min_commission_test`; the result without the dividend credit; and, as information only, the main configuration with the open priced at 12 bp (a copy of kit/extra_costs.json with the class's spread_bps_open set to 12, given through EXPLORE_EXTRA_COSTS to a separate process; never judged) | Post-earnings-announcement drift, strongest after the largest surprises (Bernard and Thomas 1989; the announcement return as the surprise: Brandt, Kishore, Santa-Clara and Venkatachalam 2008). On the lab's 40 shares the drift was nil below 5 % and, at 8 % or more, +128 bp gross from the next open to the fifth close (83 events): a hypothesis from one sample, tested here on another. Survivors only (today's index list): said with the result | 532 signals on 332 days, about 100 a year (counted from the signal data alone; recount with ret_total and the action flag) |
| 060 | Large earnings shocks, held for weeks | Earnings (shares, broad), slow track | Same | SLOW TRACK (declared.json "track": "slow"; judge.verdict max_hold_tdays=40). Same events, signal and entry as 059; exit at the close of the fortieth session of the hold, stop 3 x D20. Neighbours: exit at the close of the twentieth and of the thirtieth session; thresholds 6 % and 10 %; stops 2 and 4 x D20. Report how many holds cross the company's next results day, and the same reports as 059 | The classic drift runs for about sixty trading days; if five sessions catch a part, forty should catch more, at the price of swaps (about 80 bp long over forty sessions) and of the next results | Same signals as 059 (one position per share: fewer trades) |
| 061 | Large shocks on other news (8-K days that are not results) | News (shares, broad) | Same | CLOSED WITHOUT A RUN on 2026-11-18 (power): 130 signals at 8 % in five years, 88 of them in 2020; 236 at 5 % on calm sessions | - | Under 250 |
| 062 | Large moves without news in a calm market: fade them | News (shares, broad) | Same; `events_edgar.idea_sessions('062', results_ahead=0)` (sessions with no filing of the company in the last three sessions and no results day near) | A session where the universe's median absolute `ret_total` is under 2 % (a calm market), on which the share's abnormal move (as in 059) is at or beyond +/-6 %, not flagged `action`, with no filing of the company (see the function). Enter AGAINST the move at the open of the next session, exit at the close of the fifth session of the hold, stop 1.5 x D20, one position per share. Groups = sectors. Neighbours: thresholds 5 % and 8 %; exit at the close of the third and of the fourth session; stops 1 and 2 x D20. Same reports as 059 (2020 and 2021 hold two thirds of the signals: give each year) | The other half of the literature on large moves: with public news prices drift, without it they tend to revert (Chan 2003; Savor 2012). 'No filing' is not 'no news' (a broker's note, a rival's results, a lawsuit are not filed): the test reads whatever is left | 935 signals on 442 days; by year 75, 98, 104, 379, 279 (recount with ret_total and the action flag) |
