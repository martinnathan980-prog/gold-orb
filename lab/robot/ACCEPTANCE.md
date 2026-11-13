# ClaudeRobot: acceptance of the shipped file (step K)

Step K checked the single file the user installs, `dist/ClaudeRobot.mq5`, against the lab on the in-sample data
(2013-2021; every price frame and trades file is read with a filter that stops before 2022-01-01 inside the read call).
The file is translated to C++ by `check/to_cpp.py` and compiled with `g++ -std=c++17 -O2 -ffp-contract=off -Wall`, plus a
sanitizer build (`-fsanitize=address,undefined -D_GLIBCXX_DEBUG`). It runs in the replay mock (`check/mock_replay.h`),
which imitates MetaTrader 5 and a hedging broker; it is not MetaTrader. MetaEditor cannot run here: section 6 lists what
only the user's Mac can check.

**Verdict.** ⟨T6⟩ All 31 tests of the suite pass on the final tree. The shipped file makes, for every
sleeve, byte for byte the decisions and paper trades that the rule steps verified against the lab; its trades equal the
lab's on the same bars, with five kinds of classified differences (section 4); its account equals growth.engine fed its
own trades for F3S, F2S, F1S and F3S with the changes on; restarts and outages leave the later paper trades unchanged;
the broker faults, the guards and the golden self-test behave as SPEC 7 asks. Nothing found needs a code change before
the Mac compile, except the cosmetic warning of request 1 (section 5).

| File | CR_BUILD | Lines |
|---|---|---|
| `dist/ClaudeRobot.mq5` (what the user compiles) | `1ca53085c0c1` | 12,133 |
| `dist/ClaudeRobot_debug.mq5` (the same plus `CR_DEBUG`: aggregate lines, bar dump) | `0f6a32ec1ea3` | 12,134 |

Both are `tools/amalgam.py`'s output of the 24 files of `src/` (checked byte for byte by test_release.py), pure ASCII,
each file inlined once, the only include left `<Trade\Trade.mqh>`.

## 1. What step K changed

- `src/CR_Main.mqh`: S0's minute driver and startup machine (WAIT, REPLAY, RECON, LIVE) are kept as they were; every
  rule step's replay ran on them. Added: the PLAN line's `B_T` is now `LedBT()` (I and J: it passed a server time where a
  UTC stamp is expected); the INIT line shows the K1 table as parsed (`k1t=`, E); the SELFTEST line counts the golden
  vectors (`golden=322`); the REBUILD line says why it ran (`why=start|latebar|reconnect`) instead of a second LATEBAR
  line (B); the deinit line counts the masked bars per symbol (B). Calls into non-S0 functions are guarded by macros only
  the real files define, so the rule steps' tests (which still use S0's stubs) compile unchanged.
- `src/CR_Golden.mqh` (generated) and `tools/gen_golden.py`: 322 self-test vectors (T10), checked at OnInit.
- `src/ClaudeRobot.mq5`: CR_Guards.mqh is included before CR_Follower.mqh (J's note: the follower includes the guards;
  amalgam refuses a file first inlined inside another file's include guard and needed outside it).
- `check/compare.py`: `num()` reads only the exact NaN and infinity spellings (D, E, F: `what=info` was read as
  infinity); keys such as `what`, `why`, `reason`, `build` stay text; `cmp_orders` counts NQB's re-emitted order (the same
  oid for g+2 when minute g+1 had no BTC bar) apart from duplicates (F).
- `check/mock_replay.h`: `MOCK_VMAX_<symbol>` (the volume cap, default 100 lots as before); T7b raises it.
- `check/test_s0_replay.py`: runs with `InpTrade` false. Every module is real now, so a default replay trades; the S0
  contract (no order sent) is the observer's.
- New tests: `test_accept.py` (T4, T5), `test_restarts.py` (T6), `test_t7b.py` (T7b), `test_worlds_rules.py` (T8 with the
  real rules), `test_golden.cpp` and `test_release.py` (T10).
- `dist/ClaudeRobot.mq5`, `dist/ClaudeRobot_debug.mq5` regenerated.

## 2. The suite

Run on the final tree (every test's latest run started after the last edit of `src/` and the harness, all on the dist
file `1ca53085c0c1`) with
`check/run_tests.py`'s own runner (`run_one`), in groups that ran side by side (results in `check/out/tests/summary.json`
and one log per test). Times are wall-clock: up to three tests ran at once on four cores, and several tests run more
than one process.

⟨suite table⟩

## 3. Per test

### T1: clock (step A: `test_clock.cpp`, `test_clock.py`)

| Check | Count | Differences |
|---|---|---|
| UTC to server, New York, London and back; both summer-time flags; server day and week (every hour 2012-2035 and every minute within 3 h of the 96 switches) | 244,368 instants | 0 |
| NYSE full and half days against `us_holidays` (2000-2040) | 14,976 dates (383 full, 88 half) | 0 |
| BusinessDays against pandas BDay | 359,424 queries | 0 |
| AddTradingDays against `trend.add_trading_days` (all in-sample gold 4h closes, and every 30 min of 2012-2035 for 8 values of n) | 14,397 + 30,443 | 0 |
| Server weeks of the 7,965 official in-sample trades against `stake.prepare` | 15,930 stamps | 0 |
| Known closures, every 5 min and at the edges (±1 s, ±60 s), and 600,000 random queries | 6,191 gold, 6,261 US100, 1,252 crypto closures | 0 |
| Typed `InpExtraClosures` strings | 13 good, 21 bad | 0 wrong |
| RealExitMinute (every 5 min, and 1,584,429 Friday queries) | | 0 |
| The sanitizer build | every query | byte-identical answers |

The gold holiday scan of the 102 holiday dates lists 34 where a few stray bars fall inside the built-in closures (`check/out/clock/xau_holiday_scan.csv`). Its checks pass: every holiday is listed, no gold bar falls on a long-closure date, and short days end by 14:16 New York (2019-07-04 by 16:56).

### T2: bars and quotes (step B: `test_bars.cpp`, `test_bars.py`)

| Check | Count | Differences |
|---|---|---|
| Fed bars against the rebuilt frames (time, 8 prices, raw spread), 2013-2021, 4 symbols | 8,782,695 | 0 |
| The mask (SPEC 2.2, after the B1 decision): bars dropped in sample | 20 (gold, 2012-12-31 17:00-17:58 New York) | equal to an independent pandas mask |
| Gold quotes with h = 3 points (`CR_XAU_COMM_PTS=6`) against the lab frame | 3,172,964 bars | 0 (707,101 raw spreads clipped at 0, as designed) |
| Hour, 4-hour and day aggregates against goldlab; crypto h1 and ml `_h1_bid` | e.g. gold 53,131 / 14,396 / 2,333 | 0 |
| Daily cost medians | 13,818 | 0 |
| Primitives against pandas 3.0.5 (sum, mean, median, max, min, Wilder, ...) | 8.8 million values | 0 (bit for bit) |
| Mock worlds (barrier, missing minute, LATEBAR at most one per 5 min, READY, holes, half day, compaction) | 92 checks | 0 failed |

### T3: paper engine (step C: `test_paper.cpp`, `test_paper.py`)

| Check | Count | Differences |
|---|---|---|
| Random orders on the four in-sample frames with about 4,000 holes each (all entry types, OCO, wrong-side stops, trail, break-even, targets, gap-rule exits, hold extensions, both refusals, void_le) against `gl.simulate` and the lab's helpers | 49,546 orders, 17,636 lab trades | 0 |
| The simulator map's 19 scenarios | 19 | 0 |
| End to end through the driver: the ten sleeves on `CR_Rule_Script` (the lab's orders) | 7,965 lab trades | 0 (bit for bit) |
| Unit worlds (plain and sanitizer) and 9 deliberately broken engines | 59 checks; 9 of 9 caught | 0 |

### T4, T5: every rule's decisions and trades on the shipped file (K: `test_accept.py`; D-H: their own tests)

`test_accept.py` replays the whole in-sample period (2013-2021, four symbols, 8.78 million bars) through the shipped
file in one process, all ten sleeves at once, `InpTrade` false (SPEC 8's T4/T5 setting: nothing is sent). Two settings:
switches off (the official rules), and switches on (`InpK1 = InpH2 = InpS075 = 1`, `InpK1T` = the K1 folds the lab fits
on the same bars: `2019:505.84441393264945;2020:496.6915507295559;2021:465.14468666253265`). Three checks per sleeve:

1. **Same lines as the rule step verified.** Every line of the sleeve (DEC orders and records, PFILL, PEXIT, PSTOP,
   PREVISE, PVOID, PREFUSE, HOLD) is byte for byte the same, in the same order, as in the journal the rule step's own test
   checked decision by decision against the lab (with the other steps' files as stubs). So every verdict of D-H carries
   over to the shipped file, where all modules run together.
2. **The trades against the lab directly** (`compare.cmp_trades`: entry and exit minute, side, reason equal; prices
   within 1e-12 relative), against `ref_lab.py`'s trades on the frames rebuilt from the same bars, and with the switches
   on against `ref_changes.py`'s chains (the lab's own implementations of the three changes).
3. **The sanitizer build** replays both settings with a byte-identical journal (367 s switches off, 333 s on).

Switches off:

| Sleeve | Lines = step's journal | Lab trades | EA trades | Same entry, exit, side, reason | Entry / stop / exit bit for bit | Remaining differences |
|---|---|---|---|---|---|---|
| N30 | 5,963 / 5,963 | 1,642 | 1,642 | 1,642 | 1,642 / 1,642 / 1,642 | none |
| OC4 | 2,997 / 2,997 | 999 | 999 | 999 | 999 / 999 / 999 | none |
| BKB | 4,235 / 4,235 | 645 | 645 | 645 | 645 / 645 / 645 | none |
| BKE | 3,414 / 3,414 | 519 | 519 | 519 | 519 / 519 / 519 | none |
| F1B | 4,635 / 4,635 | 631 | 631 | 631 | 631 / 631 / 631 | none |
| F1E | 3,790 / 3,790 | 518 | 518 | 518 | 518 / 518 / 518 | none |
| NQB | 7,372 / 7,372 | 1,063 | 1,063 | 1,063 | 1,063 / 1,062 / 1,062 | one stop and exit 1.6e-16 relative (log, below) |
| GFP | 1,304 / 1,304 | 416 | 417 | 416 | 416 / 413 / 416 | the 2013-05-31 hole day; January 2013 stops (below) |
| GFP, lab on the kept bars | | 416 | 417 | 416 | 416 / 416 / 416 | the 2013-05-31 hole day only |
| D4H | 29,279 / 29,279 | 494 | 494 | 494 | 494 / 494 / 494 | one lab trade open at the frame end, left out |
| ORX | 3,906 / 3,906 | 1,038 | 1,038 | 1,038 | 1,038 / 1,038 / 1,038 | one lab trade open at the frame end, left out |

Switches on (the seven unchanged sleeves give exactly the lines and trades above):

| Sleeve + change | Lines = step's journal | Lab chain trades | EA trades | Same | Bit for bit | Remaining differences |
|---|---|---|---|---|---|---|
| BKB + S0.75r | 4,272 / 4,272 | 664 | 664 | 664 | 664 / 664 / 664 | none |
| BKE + K1 | 5,088 / 5,088 | 428 | 428 | 428 | 428 / 428 / 428 | none |
| F1E + H2 | 3,784 / 3,784 | 465 | 465 | 465 | 465 / 465 / 465 | none |

What the rule steps' own tests add (re-run in this suite, each passing; numbers from their reports and summaries):
- **Decisions.** N30 1,642 of 1,642 and OC4 999 of 999 decisions resolved on the lab's bars; BKB 2,915, BKE 2,356, F1B
  1,235, F1E 994 lab orders matched with bit-equal stop distances; F1 scores within 1.1e-16 of numpy (bit for bit equal to
  the in-order sum) on 2,132 + 1,753 candidates, no score within 1e-9 of the threshold; NQB 2,615 decisions, sigma within
  3.4e-16 on 2,446,140 grid minutes; GFP 443 orders and its skip set (26 calendar Fridays + 1 hole day = the lab's 27);
  D4H 14,337 decisions, ATR bit for bit at every one; ORX 1,829 orders, levels bit for bit.
- **Changes.** K1: 518 skips equal, riskbp bit for bit on 2,356 signals, no razor; S0.75r: stop distance bit for bit;
  H2: 100 held trades = the lab's 100; no refusal in sample (the lab refuses none either).
- **Holes and restarts worlds** (data holes cut into the frames, and 14 to 26 restarts) for N30, OC4, NQB, GFP, ORX, D4H.

Remaining differences on the same bars, each with its cause:
1. **NQB: one stop and its exit price, 1.6e-16 relative** (the 2021-09-10 13:31 UTC long). The lab's returns use numpy's
   log, the EA MetaTrader's MathLog (the C library's in the harness); they differ by one unit in the last place on 6,538
   of 1,469,276 US100 returns. With the C log the lab's sigma is bit for bit the EA's. Inside SPEC 7's 1e-12.
2. **GFP: 1 trade only in the EA, 2013-05-31** (a GFP hole day, SPEC 7: classified). The gold data stops at 16:39 New
   York and starts again on Sunday; the lab's 16:45 test reads that future hole and skips the Friday. The EA cannot see
   it. Live, the real position closes at 16:45 if the broker quotes.
3. **GFP against the rebuilt frame only: January 2013 stops** (3 differ, 1 beyond 1e-12: 5.8e-10 relative on
   2013-01-11). The EA's mask drops 20 gold bars of 2012-12-31 17:00-17:58 New York (the XAU rule); the rebuilt frame keeps
   them, and they seed the lab's Wilder hour ATR. Against the lab run on the kept bars the stops are bit for bit.
4. **D4H and ORX: one lab trade each still open at the frame end** (its exit falls in 2022): left out (SPEC 7).
5. **EA orders the lab drops** (no trade results): BKB 29, BKE 19 (18 with K1), F1B 3, F1E 3, NQB 5 orders whose window
   has no kept bar within 5 minutes (the lab's make_orders drops them by looking ahead; the paper lets them expire). GFP 0.

Against the official trades (`results/r2/recalc`, the lab's own frames, not the robot): the export rounds the bid to 2
digits (SPEC 7), which moves razor decisions: N30 1 trade (2019-05-23), OC4 1 stop exit (2018-03-05), BKE 1, F1E 2 (+1
added), NQB 1 (2018-05-25: 6.0026 against 5.9994 sigma), D4H 8 of 495; prices otherwise within 0.014 USD. FP's real
digits (SPEC 10.3, 10.6) settle this.

### T6: restarts and outages (K: `test_restarts.py`)

⟨T6 section⟩

### T7a: ledger and sizing against growth.run_one (step I: `test_account.cpp`, `test_account.py`)

The official in-sample trades of the ten sleeves (entries 2018-02-01 to 2021-12-31, 5,207 trades, 207 weeks), 1,000 EUR
at the start and each month, `CR_NO_GUARD`, through I's own driver and the mock broker, against growth.run_one on
`growth.arrays(price_level="is")`, at the lab's edges x1, x0 and x-0.5:

Every count below is the same for the EA and the lab:

| Plan, edge | Taken | Minimum lot | Caps | After the plan stop | Stop week | Final balance (EUR) | Weekly balance, largest difference |
|---|---|---|---|---|---|---|---|
| F3S x1 | 4,876 | 3 | 328 | 0 | none | 358,838.34 | 0 EUR |
| F2S x1 | 4,873 | 5 | 329 | 0 | none | 357,574.41 | 0 EUR |
| F1S x1 | 4,860 | 19 | 328 | 0 | none | 319,480.88 | 0 EUR |
| F3S x0 | 4,266 | 2 | 293 | 646 | 183 | 36,837.66 | 0 EUR |
| F2S x0 | 4,263 | 5 | 293 | 646 | 183 | 36,525.37 | 0 EUR |
| F1S x0 | 4,218 | 18 | 293 | 678 | 182 | 37,578.00 | 0 EUR |
| F3S x-0.5 | 1,151 | 2 | 76 | 3,978 | 49 | 8,829.43 | 0 EUR |
| F2S x-0.5 | 1,147 | 6 | 76 | 3,978 | 49 | 8,827.73 | 0 EUR |
| F1S x-0.5 | 1,511 | 18 | 100 | 3,578 | 67 | 12,109.42 | 0 EUR |

Per trade, lots, m, w, unit, B, P_in and rate are bit for bit equal to a recording copy of the engine. F3S x1 and x-0.5
under the sanitizer give the same; with each deposit's deal 45 s before the balance shows it (R16), 1,210 sizing waits
and the same result. Unit worlds: 326 checks in each of four builds (plain, sanitizer, each with and without
`CR_NO_GUARD`), 0 failed.

### T7b: the whole EA against growth.engine (K: `test_t7b.py`)

The shipped file (harness build with `CR_NO_GUARD`, SPEC 7) trades on a demo account in the mock from 2018-02-01 to
2021-12-31: all ten real rules, J's follower and broker, I's ledger and sizing. 1,000 EUR at the start (InpPlanStart =
the start) and 1,000 EUR on the first of each month (46 deposits, 47,000 EUR in all), fast mode, no broker commission on
gold (SPEC 1 and 7: the exported spread already holds the lab's commission), no volume cap (the lab's engine has none).

The reference is growth.run_one, and I's recording copy of growth.engine (bit for bit the same, checked), fed the EA's
own trades and payments: one trade per sizing request of the EA (its SIZE line), with the stamp as entry time, the EA's
own close stamp from the deal (SPEC 5: a broker stop hit in minute X is booked at X + 60 s, an EA close at X), the paper
fill as entry price, the
EA's sizing risk r of SPEC 4.2 (with a change on: r / f, the frozen stake factor), and the money the account booked
(side x (real exit - real entry)).

| Plan | Requests | Taken EA / lab | Minimum lot EA / lab | Caps EA / lab | Stop week | Weekly balance, largest difference | Lots differing | Final balance EA / lab (EUR) |
|---|---|---|---|---|---|---|---|---|
| F3S | 5,190 | 4,859 / 4,859 | 4 / 4 | 327 / 327 | none / none | 2.9e-11 EUR | 0 | 382,133.78 / 382,133.78 |
| F2S | 5,190 | 4,857 / 4,857 | 6 / 6 | 327 / 327 | none / none | 1.2e-10 EUR | 0 | 367,350.92 / 367,350.92 |
| F1S | 5,190 | 4,852 / 4,852 | 11 / 11 | 327 / 327 | none / none | 5.8e-11 EUR | 0 | 335,437.33 / 335,437.33 |
| F3S, switches on | 5,062 | 4,745 / 4,745 | 4 / 4 | 313 / 313 | none / none | 1.2e-10 EUR | 0 | 471,652.95 / 471,652.95 |

Money paid in by week: equal in every week (largest difference 0). The weekly balance differences (at most 1.2e-10 EUR)
come from the order in which the two engines add the same amounts.

Listed, never silent (SPEC 7 T7b):
- **P1** (late gold intents sized on the larger of paper risk and quote risk, SPEC 4.2): the quote risk was larger on
  ORX 163, GFP 95 and D4H 87 requests (the largest ratio 1.30), and the lots came out smaller on ORX 114, GFP 41 and D4H
  60 of them under F3S (F2S 108, 37, 62; F1S 99, 38, 56; F3S with the changes 113, 41, 65). The reference is fed the EA's
  r, so these are listed, not differences. SPEC 4.2 estimated 16 of 495 donch, 20 of 1,039 orb and 0 of 414 GFP trades
  over 2013-2021; 2018-2021 alone has several times more, because the late order goes at the next bar's quote plus h and
  the market slippage, which is often worse than the paper fill. For the lead (SPEC 4.2, 9.1).
- **P5** (`MISSED reason=exited`): 0 in this period.
- **NOT_READY**: ETH's data starts on 2018-01-01, so its 60-day depth (SPEC 2.2) is there only from 2018-03-02. The ETH
  sleeves skip their intents as NOT_READY until then: BKE 8 and F1E 9 requests (7 with H2 on), left out of the reference.
- **Open at the end**: one ORX and one D4H position (opened 2021-12-31): kept as open positions (caps), booking nothing.
- **Volume cap**: the mock's default SYMBOL_VOLUME_MAX of 100 lots would have cut 52 BKE and 90 F1E orders late in the
  period under F3S (F2S 45 and 86, F1S 31 and 79, F3S with the changes 56 and 59); CR_Broker cuts them and journals
  `SEND cut=vmax`. The test raises the cap, since the lab has none. FP's real caps are a Mac item (section 6).
- **Razor r**: for a distance stop the EA sizes on stop_dist, while the lab's trade risk is |entry - stop|; the two
  differ by rounding (about 1e-16 relative) on BKB 480, BKE 446, F1B 530, F1E 490, OC4 489 and NQB 929 trades. A lot can differ only when
  its quotient falls within 1e-9 of a lot step; the reference is fed the EA's r, so none appears here.

### T8: broker faults and clean worlds (J: `test_worlds.py` with script sleeves; K: `test_worlds_rules.py` with the real rules)

J's 30 fault worlds and 3 clean worlds run the ten sleeves on `CR_Rule_Script` (the lab's own orders replayed), so they
test the execution layer alone. 34 of 34 pass, builds with 0 warnings (plain, h = 6, release, sanitizer):
- clean_fast (2021): 1,437 live paper trades, 1,348 real positions at exactly the expected entry and exit prices (market
  slippage and stop slippage on the grid stop included), 89 sizing skips because the caps were full; paper = lab for all
  1,437 trades;
- clean_tick: the same 1,348 trades, 925 exits at the exact price, the 423 broker-stop exits at the triggering tick;
- clean_h (gold with h = 3 points): 223 of 223 trades exact;
- the 30 fault worlds of SPEC 7 T8: refused stop or modify, a modify inside the freeze level, requote and timeout, a
  slow reply, a duplicate made by the broker, an N30 reversal close retried, a deal stamped after the terminal's clock,
  stops dropped by the broker or by hand, positions listed late after a restart, a restart mid-trade, a late bar, a hole
  that stays, rewritten comments with a NOT_READY sleeve, magic-0 deals, the clock 1 h off, deposits and withdrawals, the
  balance and history out of step for 30 s and 90 s, plan start unset, in the future and after manual losses, the plan
  stop, the guard (a, b, c and the mark refused while the market is closed), the daily lock, the Friday close, InpTrade
  false on the VPS, an observer off the VPS, a second and a crashed instance, P5, P4, Good Friday, the switches on demo
  and on real, the tester mode;
- the sanitizer world (Q1 2021, and two fault worlds again): identical output.

K runs the shipped file with the real rules (`InpScript` empty) in J's own harness, judged by J's own functions
(`real_vs_paper`, `lab_check`, `judge_clean`), over 2021 (the bars before 2021 are the first start's history):

| World | What | Result |
|---|---|---|
| clean_fast | fast mode, switches off | 1,437 live paper trades: 1,348 real positions, every entry and exit at the expected minute and price; 89 sizing skips (caps full); paper = lab on all 1,437 (bit for bit, except NQB: 3 stops and 1 exit within 1.9e-16 relative, section 4 item 1) |
| clean_on | switches on (K1, H2, S0.75r) | 1,380 live paper trades: 1,298 real positions exact, 82 sizing skips; BKB+S0.75r 151, BKE+K1 95 and F1E+H2 124 trades = ref_changes.py's chains, the seven others = ref_lab.py (NQB as in clean_fast) |
| clean_tick | tick mode (ticks open, low, high, close) | the same 1,348 positions; all entries exact; 925 exits exact, the stop exits at the triggering tick (the mock's model) |
| clean_h | gold with h = 3 points (`CR_XAU_COMM_PTS=6`, raw bid = lab bid + 3 points) | GFP 39, D4H 57, ORX 126 positions: entries and exits exact, the broker stop = paper stop + side x h triggers in the same bar |
| clean_san | the sanitizer build replays clean_fast | journal and deals identical (581 s) |
| gfp_holiday | R8: Good Friday 2021-04-02 with gold quoted all day (1,380 bars copied from 2021-03-26) | GFP writes one skip line at 13:30 New York (reason 1, NYSE holiday); no order, no paper trade, no position |
| us100_half | P6: the NYSE half day 2021-11-26 quoted after 13:15 (179 bars copied from 2021-11-19) | the mask drops exactly the 179 bars; N30, OC4 and NQB write the same lines (98, 39, 248) as without them |
| orx_spike | 9.5: +50 points of raw spread on the bar that makes the London range high of 2021-03-08 | H 1714.40 -> 1714.90; the short order's level 1702.883 -> 1702.833 and stop 1715.447 -> 1715.997, as computed from the bars; the real trade follows the paper |

clean_fast per sleeve (2021):

| Sleeve | N30 | OC4 | BKB | BKE | F1B | F1E | NQB | GFP | D4H | ORX |
|---|---|---|---|---|---|---|---|---|---|---|
| Live paper trades (= lab) | 212 | 130 | 145 | 146 | 147 | 136 | 289 | 46 | 60 | 126 |
| Real positions, entry and exit exact | 202 | 127 | 145 | 145 | 144 | 136 | 227 | 39 | 57 | 126 |
| Sizing skips (caps full) | 10 | 3 | 0 | 1 | 3 | 0 | 62 | 7 | 3 | 0 |

The one D4H position of 2021-08-08 closed at the bar's open because the paper's new trail stop was already past it
(section 4, item 7) is counted as exact at that open.

### T9: the hands' tests ported (J: `test_exec.cpp`, `test_hands_port.py`)

- `test_exec.cpp`: 148 checks of the broker, guards and ledger worlds (sanitizer build), 0 failed; built with the sizing
  ports as `test_hands_port.py` builds it (`-DCR_EXEC_SIZING`, plain and sanitizer), 158 checks, 0 failed.
- `test_hands_port.py`: the 64 hands' tests that SPEC 7 T9 names and the hands define (X5 does not exist in
  `test_mains.py`) pass in the plain and the sanitizer build, with identical output; where SPEC changed the hands'
  behaviour (M1, X9, K7, K8, K15, X10, O26, X8) the expected values follow SPEC and each line says so.

### T10: golden vectors and the release guard (K: `test_golden.cpp`, `test_release.py`, `tools/gen_golden.py`)

`tools/gen_golden.py` computes every vector with the lab's own code and writes `src/CR_Golden.mqh` (`--check` confirms
the file is its output). `GoldenCheck` runs at OnInit after the build-constant check; a mismatch blocks trading
(`SELFTEST ok=0`, every intent skipped as `selftest`).

| Vectors (322) | From | Compared |
|---|---|---|
| 60 clock instants (one second around the US and UK switches of 2012-2035, the gap weeks, ordinary times) | zoneinfo; `pont.server_to_utc` | server, New York and London clocks, the server clock back to UTC (the repeated autumn hour included), both summer-time flags: exact |
| 40 NYSE dates (2013-2033: full closures, 13:00 half days, open days, 2018-12-05 and 2025-01-09) | `idxus_lib.us_holidays` | exact; the rules only (`ClkHolKind`), so a typed InpExtraClosures entry cannot fail the self-test |
| 20 AddTradingDays | `trend.add_trading_days` | exact |
| 20 BusinessDays and 10 ORX time exits | pandas BDay, zoneinfo | exact |
| 30 F1 scores (24 lab candidates from the in-sample BTC and ETH frames, 6 made-up clip and dummy edges) | `ml/strategy.py` `score_model` | 1e-12 relative (the expected value is the in-order sum; numpy agrees within 1e-12) |
| 10 K1 riskbp of the lab's brk72 ETH orders | `s1_run.py:105` formula | 1e-12 relative |
| 3 risk tables (F3S, F2S, F1S) at 11 keys | `growth._pct`, `growth.SCHEDULES` | exact; the live table is put back |
| a 48-value Wilder series and SMA series (with NaNs) | pandas `ewm(alpha=1/14, adjust=False)`, `rolling(14, 9)` | 1e-12 relative, NaN at the same places |

`test_golden.cpp` (the shipped file, sanitizer build): GoldenCheck passes on the 322 vectors and gives back the live
risk table; one vector of each kind changed beyond its tolerance (clock, NYSE, AddTradingDays, BusinessDays, ORX exit,
F1 score, F1 feature, riskbp, risk-table rate and text, Wilder value and NaN, SMA value and NaN) is refused with a message
naming it; a change of 1e-14 relative passes; 0.2 ms per call. 26 checks, 0 failed.

`test_release.py`:

| Check | Result |
|---|---|
| dist = amalgam(src) now, byte for byte; CR_BUILD = sha256 of the text; debug = release + `CR_DEBUG` | yes |
| Harness constants in the dist file (`CR_HARNESS`, `CR_NO_GUARD`, `CR_DEBUG`, `CR_IDX_TRACE`, any `MOCK_`) | none; `CR_XAU_COMM_PTS` defined once, under `#ifndef`, as 6 |
| The 14 inputs of SPEC 1, in order, types and defaults | exact; `InpScript` and `InpScriptDir` only inside `#ifdef CR_HARNESS` |
| MQL5 subset (fmax/fmin, `->`, `new`, `#import`, `virtual`, `template`, function macros, `Sleep`) | none |
| Builds: harness, sanitizer, release, debug release, release + `CR_NO_GUARD`, release + `CR_XAU_COMM_PTS=0` | 0 warnings, except the known `settled` warning of the `CR_NO_GUARD` build (request 1) |
| Release build, one week of 2021 in the mock, InpTrade true | `SELFTEST ok=1 golden=322`, `INIT harness=0 comm_pts=6`, 34 orders sent |
| Release + `CR_NO_GUARD` | `SELFTEST ok=0 why=CR_NO_GUARD is set in a build without CR_HARNESS`, 0 orders, intents skipped as `selftest` |
| Release + `CR_XAU_COMM_PTS=0` | `SELFTEST ok=0 why=CR_XAU_COMM_PTS is not 6`, 0 orders |
| Harness build of a copy of the dist file with one golden F1 score changed | `SELFTEST ok=0 why=golden f1_score 0: ...`, 0 orders |
| Debug file | 313,605 BAR lines (the bar dump), SELFTEST ok |

### Speed and the sanitizer

| What (SPEC 7, 8) | Result | Limit |
|---|---|---|
| Full in-sample ten-sleeve replay, 2013-2021, 8.78 million bars, `InpTrade` false | 20.5 s (switches off), 20.9 s (on) | under 3 min |
| A start's rebuild: 172,682 minutes (120 days of gold, 60 of the others) | 0.45 s of replay for the whole process | under 5 s |
| The same full replays under the sanitizer build | 367 s and 333 s, journals byte-identical | |
| The 2021 clean world under the sanitizer (trading, J's follower and broker) | 581 s, journal and deals identical | |
| GoldenCheck at OnInit (sanitizer build) | 0.2 ms | |

With trading on, the nine-year replay takes about 11 minutes in the mock, because the EA reads the whole deal history
at least once a minute (SPEC R5) and the mock scans every deal per call (section 6).

## 4. Every remaining difference, with its cause

On the same bars, the shipped file and the lab code differ only here:

| # | Where | Count | Cause | Status |
|---|---|---|---|---|
| 1 | NQB stops and stop exits | 1 trade in sample, 1.6e-16 relative (T4); 4 trades within 1e-12 after restarts (T6) | numpy's log against the C library's log (one unit in the last place on 6,538 of 1,469,276 US100 returns); after a restart the rolling sums start from a different first minute, so their rounding differs in the last bits | inside SPEC 7's 1e-12 |
| 2 | GFP hole day 2013-05-31 | 1 trade only in the EA | the gold data stops at 16:39 New York; the lab's 16:45 test reads that future hole | classified (SPEC 7) |
| 3 | GFP January 2013 stops, rebuilt frame only | 3 stops, 1 beyond 1e-12 (5.8e-10) | the EA's mask drops 20 gold bars of 2012-12-31 that seed the lab's Wilder ATR; equal on the kept bars | classified; request 5 |
| 4 | D4H, ORX | 1 lab trade each open at the frame end | its exit falls in 2022 | left out (SPEC 7) |
| 5 | EA orders without a lab order | BKB 29, BKE 19, F1B 3, F1E 3, NQB 5 | no kept bar within the 5-minute window: the lab drops them by looking ahead, the paper lets them expire; they never trade | no trade difference |

Execution and account differences (the paper is unchanged in each case):

| # | Where | Count | Cause | Status |
|---|---|---|---|---|
| 6 | Late gold intents sized on the larger of paper and quote risk (P1) | 2018-2021, F3S: quote risk larger on ORX 163, GFP 95, D4H 87; lots smaller on ORX 114, GFP 41, D4H 60 | SPEC 4.2: a stop, limit or OCO fill is sent one bar late at the quote | SPEC 9.1; far more than SPEC 4.2's estimate for 2013-2021 (16 donch, 20 orb, 0 GFP): for the lead |
| 7 | D4H 2021-08-08 (gold flash crash) | 1 trade: the real exit is 0.12 USD per oz better than the paper's (5.56 USD on 0.47 lots) | the paper's new trail stop was already past the next open: the follower closes at the open (SPEC 4.4), the paper books its stop there with stop slippage | SPEC 9.4 |
| 8 | Tick mode stop exits | 2021: 423 of 1,348 real exits fill past the stop | the mock's four ticks a minute (open, low, high, close) | mock model |
| 9 | ETH sleeves NOT_READY until 2018-03-02 | BKE 8, F1E 9 intents in February 2018 | ETH's data starts 2018-01-01; SPEC 2.2 needs 60 days | SPEC 2.2 |
| 10 | Restarts | see T6 | start-up windows and outages delay real entries and exits; the shared account then takes slightly different lots, and a cap can bind differently later | SPEC 4.8, 9.9 |
| 11 | Volume cap | 2018-2021 F3S: 52 BKE and 90 F1E orders above 100 lots | CR_Broker cuts at SYMBOL_VOLUME_MAX (`SEND cut=vmax`); the lab has no cap | FP's real caps: Mac item 10.6 |

Against the official trades (the lab's own frames, not the robot), the 2-digit export moves razor decisions: N30 1, OC4
1, BKE 1, F1E 2 (+1 added), NQB 1, D4H 8 of 495; prices otherwise within 0.014 USD (Mac items 10.3 and 10.6).

## 5. Requests and decisions for other owners

Step K edited only its own files and the shared S0 files it took over (CR_Main.mqh, ClaudeRobot.mq5, compare.py,
mock_replay.h, test_s0_replay.py). These requests need another owner:

| # | Owner | File | Request | Why |
|---|---|---|---|---|
| 1 | J | `src/CR_Guards.mqh` | Move `bool settled = LedSettled();` in `GrdOnTimer` inside the `#ifndef CR_NO_GUARD` block. | A `CR_NO_GUARD` build (T7a, T7b, test_release's forbidden build) warns "unused variable 'settled'". The shipped build is not affected. |
| 2 | I and J, then K | `src/CR_Ledger.mqh`, `src/CR_Broker.mqh`, `src/CR_Types.mqh` | Move `CR_MAGIC_ROBOT_LO/HI` (20261201, 20261289) to CR_Types.mqh and drop the copies (`CR_BRK_MAGIC_LO/HI` in CR_Broker). | Asked by I and J. K cannot add them to CR_Types alone: the copies in I's and J's files would then be defined twice. |
| 3 | C | `src/CR_Paper.mqh` | Add count/at accessors for the pending queue, the rule exits and the trade order. | Asked by J: CR_Follower reads `g_pap_q`, `g_pap_qn`, `g_pap_x`, `g_pap_xn`, `g_pap_t` directly (read only). |
| 4 | I | `src/CR_Sizing.mqh` | Optional: use `RegStakeFactor` once it moves to CR_Types (SizFactor is a copy). | Asked by I. |
| 5 | Lead | `check/export_frames.py` (S0) | Decide whether the rebuilt frame drops the 20 gold bars of 2012-12-31 17:00-17:58 New York. | G agreed to drop them, H had no preference. K left the export as it is: the steps' references and journals were all made on it, the effect is three January-2013 GFP stops (largest 5.8e-10 relative), and test_accept compares GFP with the lab run on the kept bars too, where it is exact. SPEC 2.2 already states the 20 bars. |
| 6 | Lead | `SPEC.md` | The wording changes the steps asked for (listed below). | Not K's file. |
| 7 | Lead, then I, J, K | `SPEC.md`; `src/CR_Sizing.mqh`, `src/CR_Guards.mqh`; K's tests | PROTOCOL_V3 Addendum G (committed at 08:16, after this suite had started) makes D2 the robot's stake plan (10 % per trade below 3,000 EUR, 5 % below 10,000, 2 % below 20,000, then 1 %, read on max(balance, money paid in), no plan stop) with the -50 % guard switched off. The shipped file follows SPEC v2 (F3S, guard on) and cannot run D2: `InpRiskTable` refuses a rate above 5 % (SPEC 1, `CR_SIZ_PCT_MAX`), so `0:10;3000:5;10000:2;20000:1` stops the EA at OnInit; the guard has no switch (SPEC 6.2); the plan stop can be kept from arming only by an `InpStopArmPaid` above any sum that will be paid in. | The lead updates SPEC 1, 5 and 6 (cap, default table, plan stop, guard); then I raises the cap and runs T7a on D2 (it is in `growth.SCHEDULES`), J adds the guard switch, K adds a D2 golden table, updates test_release's inputs, runs T7b on D2 and regenerates dist. |

SPEC wording asked by the steps (for the lead):
- §3 N30 and OC4 (D), F1 (E) and NQB (F): their orders carry `void_le` (the lab's own "exit after entry" filter); §7's
  HOLE_RULE then needs no exception for them.
- §3 NQB (F): "running sums as pandas makes them", not "re-summed daily"; the [g+1, g+2] window is one order for g+1, sent
  again for g+2 only when g+1 has no BTC bar.
- §3 GFP (G): the ATR is "the last UTC hour with bars that ended by 13:30"; in sample the lab's skip set is the 26
  calendar Fridays plus one hole day (2013-05-31).
- §4.1 (J): the "masked (bid-flat)" clause no longer applies after B1.
- §4.8 D4H row (H): "the latest 4h boundary at or before o" is not always an upper bound (a Friday 23:59 server decision).
- §5 (I): "a withdrawal moves neither B/ref nor the risk rung" holds only while B <= P_in.
- §7 (E, H): "rounding changed no trade" is not true on the 2-digit export: BKE 1, F1E 2, D4H 8 trades of the official
  frames differ on the rebuilt ones (EA and lab agree on the same bars).
- §2.1 (A): the last gold bar on short holidays starts between 11:59 and 14:16 New York.
- §4.2 / §9.1 (K, from T7b): late intents sized on the quote risk are far more than the SPEC's estimate (see T7b).

## 6. What only the user's Mac (or the lab) can check (SPEC 10)

Until each item is settled, its default holds; items 1 and 2 block trading until done.

| # | Item | What to look at | Default meanwhile |
|---|---|---|---|
| 10.1 | MetaEditor compile and the self-test on the real compiler | `dist/ClaudeRobot.mq5` compiles with 0 errors and 0 warnings; the first journal lines show `SELFTEST ok=1 why= golden=322` and `INIT ... k1t=` with the K1 table as typed. The file keeps SPEC 1's subset (no pointers, templates, function macros, fmax/fmin, Sleep; ASCII; checked by test_release.py and to_cpp.py), but MetaEditor's own warnings (implicit conversions, a member array of class objects such as `CrRollSum m_s2[2]` in NQB) cannot be proven here. Golden doubles allow 1e-12 relative, so a compiler that fuses or reorders operations still passes; times and dates are exact. | no trading |
| 10.2 | Strategy Tester run of the debug file on FP 2021 | real ticks (else 1-minute OHLC), `InpTrade` false, the three switches set explicitly; replay the dumped BAR lines in the harness in tester mode (R12): the journal must match line for line. | no trading |
| 10.3 | What `MqlRates.spread` holds | the bar's minimum spread or the closing one, against the ReleveFP files. The export rounds the bid to 2 digits; on the official frames this moves N30 1, OC4 1, BKE 1, F1E 2, NQB 1 and D4H 8 trades (section 3, T4). | ask = bid + spread |
| 10.4 | Server = New York + 7 h across a summer-time switch | the CLOCK line stays quiet in March and November. | the rule; CLOCK (SPEC 6.5) |
| 10.5 | FP sessions, crypto weekends, Friday close, holiday hours | the lab writes `InpExtraClosures` for the next 12 months (at most about 6 windows or 14 dates fit in MetaTrader's 255 characters). | built-in closures, shortened by the broker's sessions |
| 10.6 | Symbol specifications | digits, contract sizes, the US100 minimum lot, EUR tick values, stops and freeze levels, filling, margin, hedging, and **SYMBOL_VOLUME_MAX**: in T7b a 100-lot cap would have cut 52 BKE and 90 F1E orders of 2018-2021 (CR_Broker cuts them and journals `cut=vmax`). | read live; the harness uses fp_costs.json and 0.89 |
| 10.7 | Deposits and withdrawals as `DEAL_TYPE_BALANCE`; a closing deal carries the closing request's magic | the guard's mark (magic 20261290); the minimum-lot mark trade covers the other case. | the history; B(T) from the balance |
| 10.8 | Stop deals' magic and reason; comments kept | `LatestExit` reads `POSITION_TIME`, the comment only cross-checks. | position id, magic and time |
| 10.9 | VPS history depth, `SERIES_SYNCHRONIZED`, replay time, Max bars 500,000, `TERMINAL_VPS` | the four READY lines; the REBUILD line's `ms` (in the mock a start rebuilds 120 days of gold and 60 of the others in about 0.45 s). | NOT_READY until deep and complete |
| 10.10 | Tick timing, open slippage, LATEBAR rate | journal SEND/FILL against the paper; LATEBAR lines. | 2 s grace, one rebuild per revision |
| 10.11 | FP's gold commission | `COST` lines: `DEAL_COMMISSION` of the first gold fills against 0.06 USD per oz. | 6 points; a gap over 1 point is pushed |
| 10.12 | Two shadow weeks | `InpTrade` false on the VPS and on the Mac; both journals against a harness replay of the same bars; then `InpTrade` true. | none |
| 10.13 | Before real money | the user is told that the -50 % guard stays under F3S (it binds in about 2.5 % of half-edge paths) and confirms F3S; `InpPlanStart` is set; the three switches stay off on the real account until their demo period is judged. Addendum G's choice of D2 changes this item (request 7). | no real-money trading |
| 10.14 | K1 thresholds | the lab gives T(2026) with 17 digits as `2026:T` in `InpK1T`, then each 1 January. | K1 off |

Found during the build, also for the Mac:
- **MathLog.** NQB's sigma uses log returns. numpy's log and the C library's differ by one unit in the last place on
  6,538 of 1,469,276 US100 returns; MetaTrader's MathLog is a third implementation. The effect stays near 1e-16 (inside
  SPEC 7's 1e-12), but a decision exactly at the 6-sigma threshold could flip (none lies within 1e-9 in sample).
- **History reads.** The EA reads the whole deal and order history (`HistorySelect(0, now + 1 day)`, SPEC R5) at least
  once a minute. In the mock, which scans every deal per call, nine years of trading take 11 minutes of replay against about 20 s
  without trading. The terminal's own cost with years of history is unknown: watch the timer's load on the VPS.
