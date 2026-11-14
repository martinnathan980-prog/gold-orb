# Round 6 (night_fade): public sources on night scalpers

Collected 2026-11-14 by the design stage of round 6, before any computation on prices. Each entry: the source, what the
robot does, and any real evidence. These notes ground PROTOCOL_V3 Addendum L; they are not results.

## 1. Night Scalper Multi (MQL5 Code Base 16350, AM2 / Andrey Kornishkin, MT5, free source, 2016-2017)

- Sources: https://www.mql5.com/en/code/16350; https://www.mql5.com/en/code/download/16350/NightScalper.mq5; https://www.mql5.com/en/forum/167140; https://github.com/KonzACDC/MQL5_MT5_EA; https://doc.stocksharp.com/ja/api-examples/2343_Night_Scalper
- Window: I read the source in full. New trades are allowed from the 'Start' hour (19:00 for the USDCAD and NZDUSD presets, 20:00 for GBPUSD) until midnight, terminal time. Any open position is closed at the first new chart bar after 00:00 terminal time. The terminal's GMT offset is not stated. On the usual GMT+2/+3 'New York close' broker clock this is 12:00/13:00-17:00 New York, with the forced exit exactly at the 17:00 NY rollover. That is the US afternoon up to the close, not the Asian night.
- Pairs: Presets for USDCAD, GBPUSD and NZDUSD (up to 9 symbols). Checked once per new bar of the chart timeframe (H1 in the author's tests).
- Entry: Bollinger Bands on the chart timeframe, current bar. Buy at market if Ask < lower band; sell if Bid > upper band. Only allowed when the band width (upper minus lower) is below 'Razmah' points, which acts as a narrow-channel gate. One position per symbol. Presets: USDCAD BB(40,1) with width < 450 points; GBPUSD BB(8,1) < 200; NZDUSD BB(4,1.2) < 450.
- Exit: Fixed TP of 20/80/40 points (2/8/4 pips on 5-digit quotes). Fixed SL of 370/450/410 points (37/45/41 pips), so the stop is 5 to 18 times the target. Forced market close after midnight.
- Filters: Only the band-width cap. No spread, weekday, news or rollover filter.
- Real evidence: None. There is only an optimisation screenshot (Jan-Sep 2016, H1). The GitHub file NightScalper.mq5 (KonzACDC/MQL5_MT5_EA) is byte-identical to this code. StockSharp sample 2343 is a port with the same defaults (USDCAD preset). Neither is independent evidence.

## 2. MQL5 article 4102 'Night trading during the Asian session: How to stay profitable' (D. Zabudskiy, Jan 2018, code in the article)

- Sources: https://www.mql5.com/en/articles/4102
- Window: Code default is 22:00-03:00 terminal time, wrapping midnight. The offset is not stated; on a GMT+2/+3 NY-close clock that is 15:00-20:00 NY. The optimised run used 01:00-11:00 Moscow time (UTC+3), which is 22:00-08:00 UTC: 18:00-04:00 NY in winter, 17:00-03:00 NY in US summer. All positions are closed when the window ends.
- Pairs: EURUSD on M30 is the main test. AUDUSD, GBPUSD, NZDUSD, USDCAD and USDCHF were also tested. The author found EURUSD, NZDUSD and AUDUSD 'most suitable'.
- Entry: Bollinger Bands (default 12 periods, 2 SD; optimised period 11), current bar. Sell when the ask is within a few points of the upper band; buy when the bid is within a few points of the lower band (touch zone set by div_work/div_signal). An opposite signal closes the trade and reverses it.
- Exit: Fixed TP and SL in points (defaults 50/100; optimised TP 120, SL 140 = 12/14 pips). Everything is closed at the end of the window.
- Filters: Weekday switches (the optimised run skips Tuesday). No spread, news or rollover filter. Costs are not discussed.
- Real evidence: Backtest only (Halifax, 2017, AUD 100 deposit). About +152% on 'OHLC on M1' against +48% on real ticks. The author blames history quality for the gap and calls the band signals 'not accurate enough'. No live record.

## 3. MQL5 article 1373 'How Reliable is Night Trading?' (S. Shashev, Aug 2013, template EA in the article)

- Sources: https://www.mql5.com/en/articles/1373
- Window: The night flat is taken as 18:00-10:00 server time. The template trades from h_beg = 20:00 to h_end = 10:00 server. The server offset is not stated and the article was written on a Russian-broker clock, so the NY conversion is uncertain (13:00-03:00 NY if the clock is GMT+2/+3 NY-close).
- Pairs: EURCHF, EURCAD and GBPCAD, named as the night pairs that Alpari PAMM night accounts traded in 2012-2013.
- Entry: At 20:00, the 'flat boundaries' are the highest high and lowest low of the two previous bars. Sell at market when Bid goes above that high; buy when Ask goes below that low. At most one buy and one sell per night: the author says a second entry 'often results in closing with a loss by the end of the night flat'.
- Exit: TP 'quite close, from 10 to 50 points' (code: 20 points from the boundary). SL 'greater than TP, from 30 to 70 points' (code default 90). Everything is closed at h_end.
- Filters: Time only. The author lists volatility analysis, news (intervention risk) and the underlying majors as improvements still needed.
- Real evidence: The author claims it 'earned around 50% per annum over 6 months' on a real account, with no statement shown. His practical findings: night spreads are 1.5-2x wider on EURCHF, GBPCAD and EURCAD. The EURCAD target had to be cut from 40 to 20 points between winter and summer. 'Night trading offers good profit opportunities in winter', less in spring and summer. Interventions on EURCHF/USDCHF can bring large losses.

## 4. PolyFitScalper v1.57 (igorad, forex-tsd 2009, open source, reposted on the MQL5 forum)

- Sources: https://www.mql5.com/en/forum/179781; https://c.mql5.com/forextsd/forum/164/polyfitscalper_v1.57.mq4; https://c.mql5.com/forextsd/forum/164/schedule1.txt
- Window: Alpari UK server, on UK time (GMT+0 winter / GMT+1 summer, i.e. New York + 5 h). StartHour 22 and EndHour 8 give 17:00-03:00 New York; Friday ends at 22:00 server. The default Schedule1.txt narrows trading to hand-picked slots, for example 21:30-22:50, 00:45-01:15, 01:30-01:45, 02:30-02:50, 04:15-06:00 and 06:30-06:55 server (16:30-17:50, 19:45-20:15, 20:30-20:45, 21:30-21:50, 23:15-01:00 and 01:30-01:55 NY), plus 19:15-20:15 (14:15-15:15 NY).
- Pairs: EURGBP on M1 by default; a second set for EURCHF on M1. GBPCHF is mentioned.
- Entry: A linear regression line (polynomial degree 1) over the last 150 M1 closes, with bands at +/-3.0 standard deviations (up to 3.7). Buy when Ask is below the lower band; sell when Bid is above the upper band. Up to 3 positions are layered at 3.0/3.35/3.7 sigma, a limited form of averaging.
- Exit: Close when price returns to the middle line (ProfitRatio 0.5), once profit is at least 1 pip and the trade is at least 1.5 minutes old. Initial SL 45 pips. Optional fixed close time.
- Filters: The schedule file sets minute-level hours per weekday. The author recommends a low-spread broker and ships a spread meter. No news filter.
- Real evidence: Only demo forward tests posted in the thread (2009). Useful mainly as an explicit example of curve-fitted night hours.

## 5. Night Hunter Pro (Valeriia Mishchenko, MQL5 Market MT4 66358 / MT5 68327, June 2021, 2,800 USD)

- Sources: https://www.mql5.com/en/market/product/66358; https://www.mql5.com/en/market/product/68327; https://www.mql5.com/ru/blogs/post/745616; https://www.mql5.com/en/signals/856903; https://www.mql5.com/en/signals/856907; https://newyorkcityservers.com/blog/night-hunter-pro-review
- Window: Server clock GMT+2 with US DST ('used by most brokers'), so 00:00 server = 17:00 NY. The order hours are hidden behind a 'Smart Time Filter' and not published. A third-party review says about 21:00-01:00 broker time (14:00-18:00 NY); this is unverified. A Friday stop hour of 22:00 server (15:00 NY) is recommended to avoid holding over the weekend. The signals show an average holding time of 11 h.
- Pairs: EURUSD, GBPUSD and EURCHF are the '3 best' ('most liquid ... night scalping usually works best on these pairs'). Also USDCAD, USDCHF, CHFJPY, AUDCAD, EURCAD, EURAUD. M5, run from one chart.
- Entry: Pending (limit) buy and sell orders placed around price at night. 'Minimum Price Range' is the minimum distance between the buy and sell pending orders, in % of ATR (0-20). The exact level logic is not disclosed.
- Exit: Take profit ('most of the trades are closed using TP'). Fixed SL in pips, set per pair, which can be hidden. A close on floating drawdown. A Friday close.
- Filters: A max spread for pending orders (cancels them) and a separate one for closing. A rollover time filter. A news filter. A negative-swap filter (no Wednesday-evening trades in the negative-swap direction). A Christmas/New Year filter. A cap on net exposure to the same currency (2 recommended). Splitting orders to limit slippage (single entries of at most 0.2 lot).
- Real evidence: Real IC Markets signals. 856903 '9 pairs', since 2020-10-27: 2,587 trades, 67.9% winners, PF 1.21, average win 0.65 against average loss 1.15 AUD (one loss = 1.8 wins), +195% with no deposits (about 1.5%/month), balance drawdown 21.9%. 856907 'all pairs': 2,185 trades, 67.6% winners, PF 1.22, +139%. Four other advertised signals (856906, 1046432, 1067804, 1067812) no longer exist. Several product reviews report losses after 2022.

## 6. Scalp IC Markets ECN (MQL5 signal 683917, MT4) and Scalp IC Markets MT5 (signal 1560883), Roman Kartezhnikov - rules not published

- Sources: https://www.mql5.com/en/signals/683917; https://www.mql5.com/en/signals/1560883
- Window: Not published. The description says 'Night scalping ... a virtual stop loss is applied at about rollover time due to greatly increased spreads'. A subscriber review (Oct 2026) says the system 'operates around the market rollover period (late night / market close and open)'. Average holding time is 2 h (1 h on the MT5 account), about 5 trades per week.
- Pairs: Deals on 683917: GBPCAD 740, EURAUD 453, EURSGD 348, EURCAD 189, GBPUSD 154, CHFJPY 133, XAUUSD 132, USDCAD 125, EURGBP 125, GBPAUD 95, EURUSD 90, EURCHF 63, AUDCAD 36. The MT5 account trades GBPCAD, GBPAUD, EURSGD, EURAUD, GBPUSD, EURCAD, EURGBP, AUDCAD, XAUUSD, CHFJPY, AUDNZD.
- Entry: Not disclosed. The description says no martingale and that news is taken into account.
- Exit: 'Each order has its own fixed stop loss ... and take profit', with a hidden (virtual) stop around the rollover spike.
- Filters: News (stated). Broker-specific: copiers are told to use low-spread ECN accounts, ideally the same broker.
- Real evidence: Real ICMarkets-Live18 account, public since 2020-07-14 (history from 2019-08): 2,718 trades, 70.45% winners, PF 1.79, average win 3.43 against average loss 4.56 EUR (one loss = 1.33 wins), +8,549%, balance drawdown 23.2%, equity drawdown 38.4%, deposit load up to 35%. MT5 account since 2022-06-08: 2,637 trades, 72.65% winners, PF 1.58, average 0.65 against 1.09 EUR, equity drawdown 32.9%. A subscriber's copy test found a tracking error of about 1 pip at 3x size, about 4 pips at 8x and 8-12 pips at 20x. This is the longest clean public record of a night scalper found.

## 7. Luna AI PRO (Profalgo Limited / Wim Schrynemakers, MT4 101970, July 2023; successor of the delisted 'Night Owl' 68713/84775)

- Sources: https://www.mql5.com/en/market/product/101970; https://www.mql5.com/en/blogs/post/753391; https://www.mql5.com/en/signals/1502590
- Window: Start and stop times are set on GMT+2 winter / GMT+3 US-summer broker time, 'assuming rollover at 0:00', i.e. referenced to 17:00 NY. The default hours are not published. A per-pair rollover filter has its own start and end times. Options exist for Friday evening and the weekly open. Average holding on the signal is 4 h.
- Pairs: EURAUD, EURCAD, EURCHF, GBPCHF, AUDUSD, AUDCAD, EURGBP, GBPAUD (the signal now trades EURAUD, AUDUSD, AUDCAD, GBPAUD). M5.
- Entry: A 'mean-reverse strategy' that uses Bollinger Bands (the manual's error message names the indicator). Limit orders by default, or a market order if the limit is out of range. Levels are not disclosed.
- Exit: SL and TP per pair; the TP can be moved by X pips, and SL/TP can be set after the fill to avoid levels distorted by slippage.
- Filters: Max spread to enter. A spread level at which pending orders are deleted. A rollover filter for pairs with big rollover slippage. A cap on correlated trades (3 suggested). US holidays skipped. A triple-swap / maximum swap-cost filter. A news filter (including AUD pairs on JPY news). Per-pair lot reduction when a pair performs badly.
- Real evidence: Real IC Markets MT5 signal 1502590, public since 2022-04-27 (history from 2018): 2,533 trades, 88.9% winners, PF 1.24, average win 2.15 against average loss 13.94 USD (one loss = 6.5 wins), worst trade -194.52, balance drawdown 46.8%, +239% (about 1.3%/month). Most of this record falls in the lab's 2022-2026 validation and holdout years.

## 8. SFE Night Scalper (vendor 'atractor'; MQL5 product 12156, now delisted) - independent review and Dukascopy backtests by ForexBenchmark (2019)

- Sources: https://forexbenchmark.com/eas/reviews/sfe-night-scalper/; https://www.myfxbook.com/members/atractor/sfe-night-scalper/1393341
- Window: Per-pair lists of server hours on a NY-close clock: hour 0 (00:00-01:00 = 17:00-18:00 NY) for most pairs, hours 0-1 for some, and 21-0/21-1/21-2 (14:00 to 17:00/18:00/19:00 NY) for CHFJPY, EURAUD and EURCHF. The reviewer: 'The most important timeframe for this strategy is the hour directly after the rollover, when the spreads are the highest. All pairs trade here and only a few trade before or right after this hour.'
- Pairs: AUDUSD, AUDCAD, CADCHF, CHFJPY, EURAUD, EURCHF, EURNZD, EURUSD, EURCAD, EURGBP, GBPCAD, GBPUSD, USDCAD, USDCHF, USDJPY, USDSGD; another set adds GBPAUD, GBPCHF, GBPNZD, NZDCAD. M5.
- Entry: 'Mean-reversion strategy on M5 time frame'; enters with pending orders. Levels are not disclosed.
- Exit: Partial exits on many trades. SL/TP levels not disclosed.
- Filters: Hours set per pair. No news filter.
- Real evidence: The vendor's live myfxbook account had 'over 4 years' of history in 2019 (myfxbook returned 403 here, so not read). The reviewer's Dukascopy tick backtests, 2010-2019, at 0.1 lot with vendor settings: hour-0 PF 0.71 (USDSGD), 0.97 (EURNZD), 1.09-1.48 for most pairs, 1.64 (EURAUD); hour-1 PF 0.93-1.30. Win rates are mostly 49-66%, with the average win about equal to the average loss (GBPCAD and EURNZD: 72-77% winners, losses 2-3x wins). Verdict: 'highly broker dependend and not very scalable'; version 6.0 'seems the author optimized' 2015.

## 9. GerFX QuantFlow Scalper, formerly 'NY Close Scalper' (Exler Consulting GmbH / Paul Exler, MT4 51340, July 2020, 900 USD); sister EAs Density Scalper, NightWalker, DeltaWave

- Sources: https://www.mql5.com/en/market/product/51340; https://www.mql5.com/en/blogs/post/737765
- Window: 'Around the New York close time (16:00 - 18:00 New York time)'; 'QFS and DS also only trades exactly one hour before and one hour after swap time'. NightWalker and DeltaWave trade up to 6 h on some pairs. DST is handled internally; backtests run on Tick Data Suite at GMT+2 with US DST.
- Pairs: EURUSD, GBPUSD, EURCHF, USDCHF, USDCAD, EURAUD, EURCAD. M5.
- Entry: 'A mean reversion strategy around the close of the New York session', based on a price channel whose calculation is not disclosed. A wait between same-side entries, extended by 15 min after a losing hour.
- Exit: Fixed stop loss on every position; TP not disclosed. On Density Scalper the SL can be cut to a fraction of normal 30/45/60 minutes after swap time ('a larger SL before the spread spike at swap time and a smaller SL afterwards').
- Filters: Max spread (set per pair automatically). No trades before swap time on negative triple-swap days. A news filter (high impact, central-bank events, speeches) plus a 'breaking news' filter. A stock-market-crash filter (no trading if the S&P 500 fell more than a threshold over the last 8 h). A Christmas-New Year pause. A daily equity stop measured from 17:00 GMT. Caps on total positions and on positions per currency. The author also says to turn it off around elections.
- Real evidence: Signal 417005 has been deleted. Author's own statements: the maximum backtest drawdown is about 56 USD per 0.01 lot over 16 years, and it happened in 2008; 'flash crashes can cause big losses for night scalpers' (Jan 2019); spreads 'can go up to 20 pips after swap time'; Dukascopy's early-year spreads are 'like 10 pips on average on some symbols'. His backtests use 5 USD commission and a 150-250 ms delay.

## 10. Black Night (Heiko Kendziorra, MT4 74678 / MT5 76078, Dec 2021)

- Sources: https://www.mql5.com/en/market/product/74678; https://www.mql5.com/en/market/product/76078; https://www.mql5.com/en/blogs/post/747170; https://www.mql5.com/en/blogs/post/747315
- Window: Broker clock GMT+2/+3 with rollover at 00:00 (= 17:00 NY). MT4: HourStart 22 and HourEnd 23, i.e. orders placed 15:00-16:00 NY. The vendor says it 'does not open trades in the difficult rollover hour' and 'starts trading one hour before the usual night scalping time to take profit without swap'. MT5: HourStart 22 to HourEnd 1 (15:00-18:00 NY), with low activity in the rollover hour.
- Pairs: MT4: AUDCHF, CADCHF, EURCHF, GBPUSD, GBPCHF, GBPJPY, USDCHF, EURAUD, AUDCAD, CHFJPY, GBPCAD, plus AUDUSD, AUDJPY, EURGBP, EURCAD at half size. MT5: AUDCHF, AUDUSD, AUDJPY, EURUSD, GBPUSD, EURGBP, EURCHF, CHFJPY. M5.
- Entry: The vendor: it 'uses like many night scalpers the Bollinger Bands indicator ... sets from a certain hour on limit orders at the external Bollinger Bands'. The limit order follows the band; buys and sells are handled independently.
- Exit: A hidden TP when price is a set number of points past the middle Bollinger line ('the line in the middle triggers the take profit'), a wider visible TP2, and a hard SL. Internal per-pair presets shift the SL, TP and order distance.
- Filters: MaxSpread deletes pending orders ('in the rollover hour usually all limit orders are deleted'). Filters on where price sits relative to previous days' and weeks' highs and lows. Correlated pairs are excluded once one trade is open. Lower activity on US holidays. No trading from late December to 2 January.
- Real evidence: All five advertised signals (1278063, 1280934, 1307592, 1318637, 2135693) have been deleted. The vendor writes that 'in the last week of Nov. 2021 ... many night scalpers had huge losses'. The EA is optimised for RoboForex ECN; with MetaQuotes demo tick data 'the shown test results double'; about half of the brokers' downloadable tick histories were corrupted.

## 11. Keep Sleeping EA (Dmitry Homenkov, MT5 73548, Oct 2021)

- Sources: https://www.mql5.com/en/market/product/73548; https://www.mql5.com/en/blogs/post/746449
- Window: 'Usually from 22:00 to 3:00 GMT+2(+3)' server time, i.e. 15:00-20:00 NY. Orders are set at the start and removed at the end. Pause intervals, for example 23:45-00:10 (16:45-17:10 NY) or 23:50-00:15. Remaining positions are closed at a set time, for example 04:00 server (21:00 NY). Pending orders are removed at 23:30 server on Friday.
- Pairs: GBPUSD, AUDCAD, EURAUD, EURCAD, GBPAUD, GBPCAD, GBPNZD, EURCHF, GBPCHF, USDCAD, EURGBP, USDCHF, AUDUSD, NZDUSD, EURNZD, CHFJPY. Works on M5 internally.
- Entry: Limit orders. An 'open price deviation ratio' (0-1) sets how far from market the limit sits (0 = closest, most trades).
- Exit: TP set by a 'take profit ratio' (0 = shortest target; about 30 points, i.e. 3 pips, on EURUSD on average). A trailing TP ('almost all losses are fixed by trailing TP without triggering main SL'). A 'safe SL' against spread widening. A forced close time.
- Filters: Pause intervals around the rollover, pending orders removed before the weekend, a balance stop.
- Real evidence: None (no signal).

## 12. Waiting Night MT5 (Marat Baiburin, MT5 77928, Feb 2022)

- Sources: https://www.mql5.com/en/market/product/77928; https://www.mql5.com/ru/blogs/post/749398
- Window: 'Quiet hours' at night. The user enters the broker's winter GMT offset and DST. Hours are not published. There is an option to trade the Sunday-to-Monday night. All trades close within 3-5 hours.
- Pairs: USDCAD, USDCHF, USDJPY, EURCAD, EURCHF, EURUSD, EURGBP, EURAUD, GBPUSD, CHFJPY, AUDCAD, AUDUSD.
- Entry: Market or limit orders at a computed level ('Level calculation'), gated by a per-pair volatility filter ('Koef calculation', 'Force 1/2'). The logic is not disclosed.
- Exit: A dynamic TP ('Koef for TP'). A fixed SL of 500-1000 points (50-100 pips), because 'during the rollover, the price makes strong jumps'. A limit on how long a trade can live.
- Filters: Volatility, max spread, max loss per night, max equity drawdown, limits per currency. No news filter.
- Real evidence: Signal 1738184 has been deleted. The vendor says the parameters were optimised on 10 years of Dukascopy data with floating spread and slippage.

## 13. NightVision EA (Alexander Kalinkin, MT5 60158 / MT4 version, Jan 2021)

- Sources: https://www.mql5.com/en/market/product/60158; https://www.mql5.com/en/signals/731021; https://www.mql5.com/en/signals/956328
- Window: 'Night scalping trading during the closing of the American trading session'. GMT offset and DST inputs, and a Friday switch. Exact hours are not published. The signals hold positions 14-15 h on average.
- Pairs: GBPUSD, GBPCAD, USDCAD, GBPAUD, EURAUD, EURCAD, EURGBP, GBPCHF, EURUSD, USDCHF, NZDUSD, EURNZD, USDJPY, EURCHF, AUDJPY, AUDNZD.
- Entry: Not disclosed.
- Exit: SL and TP on every trade.
- Filters: Caps on total open orders and on positions per currency and per pair in the same direction; Friday on/off.
- Real evidence: Real IC Markets signals. 731021 (MT4) since 2020-04-06: 8,245 trades, 67.6% winners, PF 1.18, average win 3.37 against average loss 5.99 USD (1.8 wins), +324%, balance drawdown 23.7%. 956328 (MT5) since 2021-03-11: 7,303 trades, 68.8% winners, PF 1.05, average 0.85 against 1.79 USD, balance drawdown 48.4%; the vendor states 'maximum historical drawdown is ~50%, or 4-5 full StopLosses in sequence'.

## 14. Night Scalper by NoCap FX (Bjorn Larsen, MT5 124331, Oct 2024)

- Sources: https://www.mql5.com/en/market/product/124331; https://www.mql5.com/en/blogs/post/769500; https://www.mql5.com/en/signals/2367552
- Window: 'Late hours (Asian session)'; the window is set by the user in broker time. The vendor's blog speaks of 'capturing consistent mean reversion targets during rollover' and says that 'at exactly 00:00 server time (rollover) ... retail brokers ... widen their spreads, sometimes by 30 to 40 pips'. 00:00 server is 17:00 NY on a GMT+2/+3 clock.
- Pairs: AUDNZD by default (AUD, CAD, NZD and CHF pairs suggested); the signal also trades NZDUSD. Any timeframe.
- Entry: At the start of the session, one Buy Limit and one Sell Limit; orders not filled are deleted at the end of the session, so dead nights give no trade.
- Exit: Fixed TP and SL on every trade (one reviewer reports a 60-pip default SL). All trades are force-closed within the chosen window.
- Filters: A raw/zero-spread account is required; a spread setup guide is sent on request. One reviewer says there is no news filter for AUD/NZD.
- Real evidence: Real Fusion Markets signal 2367552, started 2026-04-04: 34 weeks, 196 trades, 75% winners, PF 2.04, and MQL5 notes that '80% of growth [was] achieved within 8 days'. Too short, and entirely inside the lab's 2026 holdout year: not usable.

## 15. MapleLeafs EA and MilkyWay EA (Maksim Shmyrev, MT4 8698 / 10245, 2015)

- Sources: https://www.mql5.com/en/market/product/8698; https://www.mql5.com/en/market/product/10245
- Window: Start_Time 00:00 and End_Time 01:00 ('we do not recommend changing this value'). The server offset is not stated. On a GMT+2/+3 NY-close clock this is 17:00-18:00 NY, i.e. the rollover hour itself.
- Pairs: MapleLeafs: AUDCAD, EURCAD, GBPCAD, CADJPY, CADCHF, USDCAD. MilkyWay: EURAUD, GBPAUD, EURNZD, GBPNZD. M15.
- Entry: Not disclosed.
- Exit: Not disclosed.
- Filters: Max_Spread: no order is opened if the spread is above it.
- Real evidence: None (no signal). User reviews are mixed: one doubled an account on EURCAD with a fixed-spread broker; another found few trades and a net loss in a 2016 test.

## 16. Night Scalper EU (Dua Yong Rew, MT5 94219, Feb 2023) and the same author's 2017 forum thread on night-scalper filters

- Sources: https://www.mql5.com/en/market/product/94219; https://www.mql5.com/en/forum/169957
- Window: 'Trades during the quiet session one hour before and after rollover timing', i.e. 16:00-18:00 NY. The code posted in the 2017 forum thread runs from 22 to 03 server (15:00-20:00 NY on GMT+2/+3), with a Friday switch.
- Pairs: EURUSD M5 (product).
- Entry: Not disclosed.
- Exit: Not disclosed.
- Filters: A file of high-impact news (ForexFactory calendar set to GMT+0). In the forum thread: 'a night scalper contains the most common filter - time filter - max spread - slippage'; others add news and volume. The posted code uses MaxSpread = 10 points.
- Real evidence: All four advertised signals (1662008, 1735923, 85278, 1263823) have been deleted.

## 17. NightTradeEA (Mikhail Voropaev, MT4 65494, Apr 2021)

- Sources: https://www.mql5.com/en/market/product/65494
- Window: 'The advisor opens orders only for two hours between the American and Asian sessions', so around 17:00 NY. The broker's GMT offset is set by the user; exact hours are not published.
- Pairs: AUDCAD, EURAUD, EURCAD, CHFJPY, GBPAUD, GBPUSD, EURCHF, AUDUSD, USDCAD, EURGBP, EURUSD, USDJPY. M15 (M5 for some sets).
- Entry: Not disclosed.
- Exit: A stop loss on every order; the rest is not disclosed.
- Filters: Not described (ECN/raw account and VPS recommended).
- Real evidence: Signal 1389257 has been deleted. The vendor writes: 'After the unsuccessful year 2023, changes were made to the settings files'. In a reply to a review he cites a NightTrade2 drawdown of up to 40%.

## 18. Night Walker EA (Ivan Pochta, MT5 160849, Jan 2026)

- Sources: https://www.mql5.com/en/market/product/160849
- Window: 'The transition from the US session close to the Asian session open', so from around 17:00 NY. Exact hours are in the preset files, not on the page.
- Pairs: AUDCAD, EURAUD, EURGBP, GBPUSD, USDCAD, USDCHF, USDJPY.
- Entry: 'Channel-based mean-reversion': it trades when price reaches the extreme zones of a Bollinger Bands channel, confirmed by CCI and RSI. An ADX regime filter blocks trading when volatility is too low or too high.
- Exit: A dynamic SL based on the Bollinger channel width; short TPs.
- Filters: The ADX regime filter and a news filter (MT5 calendar or the ForexFactory feed).
- Real evidence: None (no signal; launched in 2026).

## 19. Other Bollinger-channel night scalpers on MQL5 Market: Night horizontal (78039), BG Robonight (22635, 2017), Night Bollinger (24758), Synevir (27003, free, 2017)

- Sources: https://www.mql5.com/en/market/product/78039; https://www.mql5.com/en/market/product/22635; https://www.mql5.com/en/market/product/24758; https://www.mql5.com/en/market/product/27003
- Window: Night horizontal: 'at night, near the rollover', starting at 20-23 server for 1-6 hours. BG Robonight: 'at the junction of the American and Pacific sessions', on an Eastern European / NY-close terminal clock. Night Bollinger: times given in UTC+2, hours not published. Synevir: 00:05-08:00 server (17:05-01:00 NY on GMT+2/+3), closing everything at 23:59.
- Pairs: Night horizontal: GBPUSD M5 by default. BG Robonight: AUDCAD, CADCHF, EURCAD, GBPCAD, AUDCHF, GBPAUD, M15. Night Bollinger: EURCHF, USDCHF, GBPCAD, M15. Synevir: EURUSD, USDJPY, M5.
- Entry: Night horizontal: trades only when the Bollinger channel is horizontal, with pending orders at the channel edges. BG Robonight: enters a set delta beyond the outer Bollinger band, only when the channel width is between a minimum and a maximum. Night Bollinger: 'price breakout from Bollinger Bands', other details kept secret. Synevir: Bollinger plus Stochastic, RSI and a maximum gap to a fast moving average.
- Exit: Night horizontal: targets at the channel centre, with trailing TP/SL. BG Robonight: fixed TP/SL or a dynamic TP from ATR. Night Bollinger and Synevir: fixed SL/TP.
- Filters: Max spread in all four (Night horizontal closes orders when the spread widens). BG Robonight has a news filter; Synevir has trade-day switches. Night horizontal and Synevir offer a one-step lot increase after a loss (martingale-like); BG Robonight has optional averaging.
- Real evidence: None (no live signals on these pages).

## 20. Range and limit-order night scalpers: Asia Balance (29386), Night Ranger (113754), Night scalper bot (96956, free), Night Swimmer (108979/113684, free), Smart Owl FX (163901), EA Night Eagle Scalper (68604), Night Zen (80400), Night Scalper EA by Robots4Forex (34215/36779)

- Sources: https://www.mql5.com/en/market/product/29386; https://www.mql5.com/en/market/product/113754; https://www.mql5.com/en/market/product/96956; https://www.mql5.com/en/market/product/108979; https://www.mql5.com/en/blogs/post/758892; https://www.mql5.com/en/market/product/163901; https://www.mql5.com/en/market/product/68604; https://www.mql5.com/en/market/product/80400; https://www.mql5.com/en/market/product/34215; https://www.mql5.com/en/market/product/36779
- Window: Asia Balance: two trading periods in server time; no trades on Friday night or Monday morning. Night Ranger: a 'strictly specified time' on a GMT+2 standard clock, Asian session. Night scalper bot: starts 10 minutes after the broker's daily open and stops 40 minutes later (17:10-17:50 NY on a NY-close clock). Night Swimmer: default 23:00-01:00 on GMT+3 (16:00-18:00 NY in US summer), 'Australian forex session', optional no-Friday. Smart Owl FX: Asian session, with a US-DST switch. Night Eagle: a user-set hh:mm window with a GMT mode and weekday switches. Robots4Forex: start and end candle hours, 'evening'.
- Pairs: Asia Balance: GBPUSD, AUDCAD, GBPCAD, GBPAUD, GBPCHF (M5). Night Ranger: EURUSD, GBPUSD, EURCHF, USDCHF (M5). Night scalper bot: 18 pairs including EURGBP, EURCHF, GBPAUD, EURAUD, EURCAD, GBPCAD, CADCHF, GBPCHF, AUDCAD, NZDCAD (M5). Night Swimmer: EURUSD, GBPUSD, EURCHF, USDCHF (M5). Smart Owl: EURUSD, GBPUSD, AUDUSD, USDCAD, USDCHF, AUDCAD, EURAUD, EURCHF, CADCHF, AUDCHF (M5). Night Eagle: CHF pairs (M5). Night Zen: EURCHF (M15). Robots4Forex: EURUSD M5 works best.
- Entry: Asia Balance: the range of the 'night corridor'. Night Ranger: a buy and a sell pending order at an evening time, at the edges of the range (per a reviewer). Night Swimmer and Smart Owl: mean reversion with a maximum-volatility gate. Night Eagle: flat-market detection. Night Zen: reversals in low-volatility areas. Robots4Forex: RSI thresholds, with optional BB/CCI/MA/ATR.
- Exit: Asia Balance: fixed SL, a floating TP at the opposite edge of the channel, and an early close based on volatility. Night Ranger: an SL in 'Basic' mode or a martingale-like 'Recovery' mode. Night Swimmer: SL/TP in points, break-even and a 'smart close'. Smart Owl: fixed SL. Robots4Forex: SL 25-200 pips and an RSI-based close.
- Filters: Max spread in nearly all; Night Eagle pauses trading after a spread spike; Smart Owl has a news filter; weekday switches.
- Real evidence: Nothing verifiable. Asia Balance's demo signal 425078 has been deleted; Night Ranger's monitoring is only on myfxbook (blocked here); the others have no signals.

## 21. Delisted or unverifiable night scalpers: Evening Scalper Pro (Mishchenko, 79339/80309), Night Owl (Profalgo, 68713/84775), StarX (ForexBenchmark review), Rollover Scalper (Alexandru Casian, 78622/78675)

- Sources: https://www.mql5.com/en/market/product/79339; https://newyorkcityservers.com/blog/evening-scalper-pro-review; https://forexbenchmark.com/eas/reviews/starx/; https://www.mql5.com/en/market/product/78622; https://www.mql5.com/en/market/product/78675
- Window: Evening Scalper Pro (page delisted, known only from search snippets): 'mean-reversion ... during the American trading session', no trades during the 0:00-1:00 bank rollover, and 19:00-23:00 according to third parties. Sources disagree whether that is GMT or broker time; on a GMT+2/+3 broker clock it is 12:00-16:00 NY. Night Owl: 'the most quiet times of the market', with user hours per day. StarX: 'around the time of the end of the NY session'. Rollover Scalper: set files 'for GMT+3 ... New York Close' charts, trading around the rollover, with no trade held more than a few hours.
- Pairs: Evening Scalper Pro: EURNZD, EURAUD, AUDNZD, NZDCAD, AUDCAD, EURGBP, GBPAUD, GBPCAD (M5). Night Owl: EURUSD, USDCHF, GBPUSD, USDCAD, GBPAUD, GBPCAD, GBPCHF, EURCHF, EURAUD, EURCAD, AUDCAD (search snippet). StarX: EURCHF, USDCHF, GBPUSD. Rollover Scalper: run from one chart (GBPUSD or EURUSD), M5.
- Entry: Mean reversion in all four (StarX: 'a single position per symbol with a small profit target'); details are not public.
- Exit: StarX: small TP, short hold. The others are not public.
- Filters: Night Owl: spread and slippage filters. Rollover Scalper: 'many filters to minimize the negative slippage'.
- Real evidence: Nothing remains. The Evening Scalper Pro and Night Owl pages redirect to the catalogue. StarX's live account 'was removed during the first drawdown'. Both Rollover Scalper signals (1473516, 1550521) have been deleted, and its author writes: 'currently the markets aren't that favorable for night scalping ... the EA might show 0% or even negative return'.

## 22. GitHub sbrakni/night-scalper 'Night Scalper Pro' (2026, built with AI help, MQL5 EA plus Python research)

- Sources: https://github.com/sbrakni/night-scalper
- Window: 17:20-20:00 New York. The window opens at 17:00 NY (= 00:00 IC Markets server) and it does not trade around the midnight rollover.
- Pairs: 11 presets: AUDNZD, EURCHF, EURGBP, GBPCAD, AUDCAD, EURAUD, USDCHF, NZDUSD, AUDUSD, USDCAD, GBPUSD. EURUSD is excluded as 'too efficient to clear costs'.
- Entry: On each closed M5 bar inside the window, one of three modes: Bollinger touch-fade, Bollinger close back inside the band, or distance from an EMA. Each has an optional RSI filter.
- Exit: TP fixed or at the mean; SL fixed or based on ATR. Optional break-even, maximum holding time, a hard flat time for the session, and a Friday guard.
- Filters: Rollover skip, a spread cap per symbol, news (MT5 calendar), a weekday filter, a daily loss stop and a drawdown breaker.
- Real evidence: No live record. Its backtests use histdata from 2022-01 to 2026-07 (in-sample 2022-2025, out-of-sample 2025-2026). That overlaps the lab's validation and holdout years, so its per-pair results and chosen parameters must not be used to pick the lab's pairs or settings. Its value here is only as a clear written statement of the same common rule.

## Consensus (research stage)

This consensus is built only from elements that several sources state. No vendor publishes its exact rule.

1) Clock. Trading happens in a short window tied to the New York close, 17:00 New York. Almost every vendor writes this as 00:00 on a broker clock set to GMT+2 in winter and GMT+3 in US summer.
- Most sources trade somewhere between about one hour before and three hours after the close (16:00-20:00 NY).
- The most cited core is the first hour after the rollover, 17:00-18:00 NY. Examples: the SFE review ('the hour directly after the rollover ... all pairs trade here'), MapleLeafs and MilkyWay (00:00-01:00 server), the free Night scalper bot (17:10-17:50 NY), NoCap ('during rollover') and signal 683917 ('around the rollover').
- Sources disagree about the rollover hour itself:
  - SFE treats it as the core hour.
  - Black Night and Evening Scalper Pro avoid it and trade before it.
  - GerFX / NY Close Scalper, Night Scalper EU and Night Swimmer straddle it (16:00-18:00 NY).
  - Keep Sleeping pauses from 16:45 to 17:10 NY.
  - Older Russian templates run all night on the European clock: article 1373 (20:00-10:00 server), article 4102 (22:00-08:00 UTC) and PolyFit (17:00-03:00 NY).
  - The AM2 Code Base EA stops trading at the close.
- Most sources do not trade Friday night and usually skip the Sunday open and holidays.

2) Instruments. The quiet crosses and dollar pairs, chiefly the EUR, GBP, CHF, CAD, AUD and NZD crosses: EURCHF, EURGBP, EURCAD, GBPCAD, EURAUD, AUDCAD, GBPCHF, CADCHF, AUDNZD, GBPAUD, EURNZD. Plus EURUSD, GBPUSD, USDCHF and USDCAD. JPY pairs are a minority (CHFJPY, USDJPY).

3) Entry: fade a short-term stretch inside a quiet channel. Sell at or above the upper edge; buy at or below the lower edge.
- The edge is most often an outer Bollinger band on M5 to M15 bars: the AM2 code, Zabudskiy, Black Night ('like many night scalpers'), Luna AI, BG Robonight, Night Walker, Night horizontal and Synevir.
- Other definitions of the edge:
  - the high/low of the bars just before the window (article 1373, Asia Balance);
  - a regression band (PolyFit);
  - symmetric buy-limit and sell-limit orders at a distance from price (Night Hunter Pro, NoCap, Keep Sleeping, Night Ranger, SFE).
- Many sources only enter when the channel is quiet:
  - a maximum band width (AM2);
  - a band width between a minimum and a maximum (BG Robonight; Night Hunter Pro's minimum range in % of ATR);
  - ADX neither too low nor too high (Night Walker);
  - a horizontal channel (Night horizontal);
  - a volatility cap (Night Swimmer, Waiting Night).
- No two sources use the same band settings: periods of 4-40 bars, 1-2 standard deviations, timeframes from M1 to H1. There is no common value, so the lab has to declare one.

4) Exit: a small target and a wider fixed stop, plus a time exit.
- The target is either the middle band / mean (Black Night, PolyFit, the GitHub and StockSharp versions) or a few pips (AM2 2-8, Keep Sleeping about 3, article 1373 1-5).
- The stop is fixed and several times the target: AM2 37-45 pips, PolyFit 45, Waiting Night 50-100. Only Zabudskiy's 14-pip stop against a 12-pip target is close to 1:1.
- The surviving live accounts win 68-89% of their trades, and their average loss equals 1.3 to 6.5 average wins.
- In lab terms (1 R = the stop distance), that means many wins of roughly 0.2-0.7 R against full 1 R losses. Before costs, roughly 60-85% winners are needed just to break even.
- The time exit closes the trade at a fixed hour: AM2 at the close; articles 4102 and 1373 and NoCap at the end of the window; Keep Sleeping at about 21:00 NY; Waiting Night after 3-5 h. Signal 683917 and Luna hold 1-4 h on average, but Night Hunter Pro and NightVision hold 11-15 h.

5) Filters.
- A maximum spread that blocks entries and cancels pending orders (almost all sources).
- Protection from the rollover minutes: a pause, deleting pending orders, or a wider or hidden stop through the spike.
- One position per pair, and often a cap on positions in the same currency.
- A news filter (many, not all).
- No trades before a negative triple swap (Wednesday).
- Christmas to New Year and US holidays off.

Simplest rule that captures what most share. This is a hypothesis built from the shared elements, not any vendor's code:
- Monday to Thursday nights, in New York time.
- A window after the 17:00 NY rollover, for example 17:00-20:00 NY, with no entries during the rollover minutes.
- On M5 bars of each pair: sell when a bar closes above the upper Bollinger band; buy when it closes below the lower band.
- Take profit at the middle band. Stop loss fixed and wider than the target.
- If neither is hit, close at market at a fixed hour the same night.
- Skip an entry when the spread is above a cap. One position per pair.

Points where the sources disagree belong in the declared single-parameter neighbours, not in the main rule:
- trading before, across or after the rollover;
- middle-band target or fixed-pip target, and whether the middle band is frozen at entry or follows price;
- band period, width and timeframe;
- stop size: fixed pips, or a multiple of band width or ATR;
- market or limit entry;
- one trade per side per night (article 1373, NoCap) or repeated entries.

A minority instead fades the whole US-session move or the distance from the session open (Newton's third law, ReturnToOpen).

Working notes with the extracted quotes and figures: /tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/round6_design/night_scalper_sources.md. Downloaded pages and source files are in /tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/round6_design/dl/. Nothing in the repository was changed, and no price data was read.

## Cautions

- Rollover spreads decide the result. Vendors report spreads of up to 20 pips after swap time (GerFX), 30-40 pips at 00:00 server (NoCap), and night spreads 1.5-2x normal on EURCHF, GBPCAD and EURCAD (article 1373). The only independent test says the strategy's core hour is the one right after the rollover, 'when the spreads are the highest'. The lab's FP cost frame scales Dukascopy's intraday spread shape but clips it at 6x, which can understate the first minutes after 17:00 NY. Either forbid entries in those minutes or cost them with unclipped real spreads, and report how many entries, stops and targets fall between 16:55 and 17:30 NY.
- FP Markets' Raw spreads on crosses are not verified (as the lab already notes). For targets of a few pips they are the decisive input. Before believing any result, record FP's live bid/ask on the chosen crosses from about 16:30 to 21:00 NY over a few dozen nights; the lab's existing spread recorder can do this. Dukascopy's own spreads were very wide in early years (GerFX: about 10 pips on average on some symbols) and do not match FP's around the rollover.
- Results depend on the broker and on trade size. Black Night: MetaQuotes demo data doubles the backtest result. Signal 683917: copy error of about 1 pip at 3x size, about 4 pips at 8x and 8-12 pips at 20x. Night Hunter Pro guide: slippage becomes significant above 0.5-1 lot per account. ForexBenchmark: 'highly broker dependend and not very scalable'. A 1,000 EUR account trading 0.01-0.1 lot is in the small-size range where these robots do best, but live slippage at 17:00-18:00 NY can still exceed the lab's 0.1-0.3 bp assumption.
- Execution model. Most vendors leave limit orders resting at the band (no spread crossed, filled on touch). The lab fills at market at the next M1 open plus slippage. A market-fill test is conservative compared with the vendors; a limit-order simulation on M1 bars is optimistic unless it requires price to trade through the level. Declare one before running and do not switch after seeing results.
- Payoff shape and costs. Small targets against wide stops give 68-89% winners, but each loss wipes out 1.3 to 6.5 wins; the surviving live accounts made PF 1.05 to 1.79. Costs are a large share of a few-pip target, so the bars of PF at least 1.12 after costs and at least 1.04 at costs x1.5 are demanding; report the result before costs as well. On M1 bars, many bars will touch both a nearby target and the stop; the lab's stop-first rule is conservative here, so report the share of such bars.
- Night tail events lie inside 2013-2021 and must stay in the test: the SNB floor removal on 15 Jan 2015 (EURCHF and every CHF cross), the GBP flash crash on 7 Oct 2016 (Asian session), the JPY/AUD flash crash on 3 Jan 2019 (GerFX: 'flash crashes can cause big losses for night scalpers'), and the last week of Nov 2021 (Black Night: 'many night scalpers had huge losses'). Interventions are a further risk (article 1373). Dropping CHF pairs or these nights after seeing results would be selection.
- Curve fitting is normal in this genre: hours set per pair (SFE's lists, PolyFit's minute-level schedule file), per-pair presets (AM2, Night Hunter Pro, Black Night, Luna), five free optimisation parameters (Waiting Night), and an author tuning a recent year (SFE v6 'optimized' 2015). The lab's test should use one window and one parameter set for all pairs, with single-parameter neighbours only, as in Addendum K.
- Survivorship and changing regimes. Of the 26 signal links printed on night-scalper product pages, 22 no longer exist, and several products are delisted (Evening Scalper Pro, Night Owl, SFE Night Scalper, StarX). The survivors made PF 1.05-1.79 with drawdowns of 22-48%. Vendors themselves report bad periods: 2008 (GerFX); 2007-2008 (the 2008 '_rdb_' EURGBP Asian-session thread, mql5.com/en/forum/179042); 2022-2023 (Night Hunter Pro reviews, NightTradeEA's 'unsuccessful year 2023', Rollover Scalper's 'markets aren't that favorable'); and summer worse than winter, with targets shrinking (article 1373). Expect years with no edge; the bar of 60% of years positive will matter.
- Clock and daylight saving. Vendors use a broker clock of GMT+2 in winter and GMT+3 in US summer, so that 00:00 = 17:00 New York. Windows quoted in GMT, Moscow time or UK time shift by one hour during the weeks of March and October-November when US and European DST differ. Define the window directly in New York time, as the lab already does, and do not convert vendor hours through a fixed GMT offset.
- Swap. A position opened before 17:00 NY and held through it pays swap, triple on Wednesday. Vendors filter negative swaps (Night Hunter Pro, GerFX, Luna) or trade before the rollover to avoid it (Black Night). A window that opens after 17:00 NY and closes the same night avoids swap entirely; if the main window crosses 17:00 NY, swaps must be charged.
- Correlation. The crosses share currencies (EUR, GBP, CAD, AUD, CHF, NZD) and move together on a dollar or risk shock. Vendors cap exposure to one currency (Night Hunter Pro 2, GerFX 2, Luna 3 correlated trades, per-currency limits in Black Night and Waiting Night). The lab's one-position-per-instrument rule does not cap this; at 7% risk per trade, several correlated stops in one night could cost 20-30% of the account. The t-statistic on daily sums and the 25% maximum share per instrument are the right protections; consider declaring a same-currency cap as part of the rule.
- Information leakage. Several public records fall in the lab's validation and holdout years: the sbrakni GitHub repo (2022-2026 backtests), the NoCap signal (2026), Kartezhnikov's MT5 signal (2022 on), Luna's public record (2022 on) and product reviews after 2022. Their per-pair profit figures must not influence the basket. Keep the list of crosses fixed in dl_round6.py before this research and pick the basket by a rule declared without them.
- Data quality at night. Article 4102 shows +152% on 'OHLC on M1' against +48% on real ticks for the same few-pip strategy, and Black Night found about half of brokers' tick histories corrupted. Before running, check each pair for missing or stale M1 bid/ask bars between 16:55 and 17:30 NY, and skip nights with gaps, as Addendum K's quote test did.
- Target against spread. On very quiet nights the distance to the middle band can be smaller than the spread (article 1373 and Night horizontal warn that the spread can exceed the size of the swings). Some sources require a minimum channel width (BG Robonight, Night Hunter Pro's minimum range in % of ATR). A minimum distance from entry to target, as a multiple of the current spread, is supported by sources and could be one declared filter.
- Sources I could not read. ForexFactory threads are behind a Cloudflare block (403 for both curl and WebFetch); I found none that were usable and relied on MQL5 forum threads instead. Myfxbook (SFE Night Scalper, Night Ranger) also returned 403. web.archive.org is blocked, so delisted product pages (Evening Scalper Pro, Night Owl) are known only from search-engine snippets. Night Hunter Pro's real hours sit behind its 'Smart Time Filter' and are not published.
