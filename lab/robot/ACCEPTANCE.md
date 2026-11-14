# ClaudeRobot: acceptance of the shipped file (step K, then the fixes of the independent review)

Step K checked the single file the user installs, `dist/ClaudeRobot.mq5`, against the lab on the in-sample data
(2013-2021; every price frame and trades file is read with a filter that stops before 2022-01-01 inside the read call).
An independent review of that file then found three major and nine minor defects (`build_reports_part2.json`, key
`review`); this edition reports their fixes, the user's stake plan D2 as the default, and the whole suite run again on
the final tree. The file is translated to C++ by `check/to_cpp.py` and compiled with `g++ -std=c++17 -O2
-ffp-contract=off -Wall`, plus a sanitizer build (`-fsanitize=address,undefined -D_GLIBCXX_DEBUG`). It runs in the replay
mock (`check/mock_replay.h`), which imitates MetaTrader 5 and a hedging broker; it is not MetaTrader. MetaEditor cannot
run here: section 6 lists what only the user's Mac can check.

**Verdict.** On the final tree the whole suite passes: 31 of 31 tests, run once, one after the other (`check/run_tests.py`, section 2). The
three major findings of the review are fixed, and each has a check that fails on the reviewed file and passes on this
one. No restart closes a position whose paper trade is still open (T6: the 53 early F1E closes and the 3 ORX closes are
gone). No order goes out in a masked minute or a known closure (the weekend crypto world). The user's plan D2 is the
default, and it equals growth.run_one and growth.engine (T7a, T7b). The minor findings F4, F5, F7, F8 and F9 are fixed in
the code and tested. F6 is fixed in the code and written step by step in SPEC 10, F10 is written step by step in SPEC
10.15, and F11 is a reading (D2 and S7 with the crypto margin at 1:2). F12, the MetaEditor compile, stays the gate before
any trading (SPEC 10.1). For every sleeve the shipped file writes byte for byte the decisions and paper trades that the
rule steps verified against the lab. Its trades equal the lab's on the same bars, apart from the classified differences
of section 4; the January 2013 GFP stops are gone, because the export now drops the gold bars the EA masks, and two
tests now fail if those bars come back. Earlier runs of the suite on the same file failed two tests on the tests
themselves, and one was cut short by a machine restart (section 2); the tests were corrected, the file unchanged, and the
whole suite was then run once more, one test after the other. No defect known to this report needs a code change before
the Mac compile.

| File | CR_BUILD | Lines |
|---|---|---|
| `dist/ClaudeRobot.mq5` (what the user compiles) | `fd6aaf01e332` | 12,367 |
| `dist/ClaudeRobot_debug.mq5` (the same plus `CR_DEBUG`: aggregate lines, bar dump) | `40dce66811c6` | 12,368 |

Both are `tools/amalgam.py`'s output of the 24 files of `src/` (checked byte for byte by test_release.py), pure ASCII,
each file inlined once, the only include left `<Trade\Trade.mqh>`. The reviewed file was CR_BUILD `1ca53085c0c1`.

Sections 0 to 6 were written on CR_BUILD `1cf1d0cab64b` (debug `415c8bd8d7fd`). The final file differs from it by one
struct member's name and nothing else; the whole suite was run again on it (section 0a).

## 0a. The final file (CR_BUILD `fd6aaf01e332`): one member renamed, the whole suite again

**The change.** The independent recheck of the fixes (`build_reports_fixes.json`, key `recheck`, verdict
ready_for_demo, point R4) noted that the struct member `group` of `CrOrder` and `CrTrade` shares its name with MQL5's
`input group` keyword, which MetaEditor may refuse. It is now `grp` (commit f0f5fb8): `src/CR_Types.mqh` (the two
declarations), `src/CR_Paper.mqh` (one copy), `src/CR_Rule_Script.mqh` (one read), `src/CR_Journal.mqh` (one write; the
journal key was already `grp`, so no journal line changes), and in the tests `check/test_paper.cpp` and
`check/test_paper.py` (the S0 copies that T3's end-to-end check builds get the same rename). Nothing else in `src/`
changed. Rebuilding with `tools/amalgam.py` today gives the shipped files byte for byte (`fd6aaf01e332`, `40dce66811c6`).

**The suite on this file: 31 of 31 pass**, each test run at least once on it, 2026-11-14, in four runs (`check/run_tests.py`, one
test after the other). The first run of all 31 was cut short by a machine restart after 10 tests (disk 11 GB free,
memory normal; the cause is not known); the remaining groups were then run one by one. A quick run before it failed
`test_paper.py` on the test itself (its S0 copies still used the old name, a compile error); the test was corrected and
the T3 pair passed in a later run.

| Run (UTC, 2026-11-14) | Tests | Result |
|---|---|---|
| quick run, before the whole suite | T10 (`test_golden.cpp` 33 s, `test_release.py` 125 s), S0 (`test_s0_build.py` 81 s, `test_s0_dbl.py` 7 s, `test_s0_refs.py` 8 s, `test_s0_replay.py` 85 s, `test_s0_script.py` 17 s) | 7 of 7 pass (`test_paper.cpp` passed too; `test_paper.py` failed on the test, as above) |
| whole suite, cut short by the restart | T4 (`test_BK.py` 248 s, `test_D4H.py` 779 s, `test_F1.py` 12 s, `test_GFP.py` 504 s, `test_N30.py` 275 s, `test_NQB.py` 341 s, `test_OC4.py` 4 s, `test_ORX.py` 38 s, `test_accept.py` 553 s), T7a (`test_account.cpp` 7 s) | 10 of 10 pass |
| the remaining groups, 04:58 to 06:51 | T7a (`test_account.cpp` 10 s, `test_account.py` 1,399 s), T2 (`test_bars.cpp` 46 s, `test_bars.py` 163 s), T5 (`test_changes.py` 249 s), T1 (`test_clock.cpp` 18 s, `test_clock.py` 73 s), T9 (`test_exec.cpp` 35 s, `test_hands_port.py` 48 s), T7b (`test_t7b.py` 587 s), T8 (`test_worlds.py` 334 s, `test_worlds_rules.py` 676 s), T6 (`test_restarts.py` 2,975 s) | 13 of 13 pass |
| T3 after the test's correction | `test_paper.cpp` 23 s, `test_paper.py` 354 s | 2 of 2 pass |

Some times are longer than in section 2 because another job shared the machine during these runs. The verdict and the
numbers of sections 0 to 6 hold for this file.

**K1's threshold for 2026.** SPEC 10.14 asks the lab for T(2026). It is `InpK1T` = `2026:417.23813245421888`
(`../results/r2/validation_hi/k1_T2026.json`): q_hi of the declared procedure on the ETH signals decided before
2025-12-25, taken from the output of the single logged 2022-2025 look (no data read again). The fit skips the high side
(E_hi = -0.065 < 0), the side the robot skips. T(2027) needs 2026 bars and stays open: until it is given, K1 is off in
2027.

## 0. The independent review's findings: what changed, and the evidence

The review of the shipped file (`build_reports_part2.json`, key `review`: verdict fix_needed, F1-F3 major, F4-F12 minor)
reproduced every acceptance number and found defects the suite did not catch. Each finding below names its change and its
evidence. "The reviewed file" is CR_BUILD `1ca53085c0c1` (commit ec43431). The seven new worlds of T8 were also run on
it (`build/fix/old_code_worlds.py`, from a read-only `git show` of that commit; `check/out/fix/old_code_worlds.json`),
and T6's new check 4 on its own T6 data (`build/fix/t6_reviewed.py`): each fails there and passes on this file. The plan
checks of F3 cannot run on it at all: it refuses a rate above 5 % at OnInit and has no `InpGuard` input.

| # | Finding | Change (SPEC v2.1, section 11 rows F1-F12, X1, K1) | Evidence |
|---|---|---|---|
| F1 | major: held F1E+H2 positions closed at every restart | F1E's `LatestExit` with H2 on is the H2 horizon (`F1H2Horizon`, the same value the paper uses); a NOT_READY sleeve's positions close at `LatestExit` only after the first READY check of the load and 10 min of NOT_READY; the READY checks run before the follower in each timer pass | T6, new check 4 (an EA-initiated close in a start-up window against an open paper trade fails): on the reviewed file's own T6 data it fails with 53 F1E closes (on, exactly the review's 53) and 3 ORX closes (1 off, 2 on: an exit inside the Presidents' Day 2020 and Good Friday 2018 closures, and one after a data hole); the re-run on this file: 0 and 0 (T6 below). T8 `h2_restart`: the reviewed file closes the review's trade (oid 152102160006) at 08:29:06 UTC, 11.4 h before its paper exit; this file adopts it and closes it at 19:55:02 UTC with the continuous run. T8 `notready_gate`: the reviewed file closes an ORX position 2 s before the first READY check; this file adopts it when gold is READY again (5 min) and closes it with the paper at the reopening; with 30 min of NOT_READY the `LatestExit` close comes exactly 600 s after the first check |
| F2 | major: a market order sent in the masked crypto weekend | a shut minute (masked for the symbol, or in a known closure) never activates a market order, and no request of any intent goes in one (`BarsShut`) | T8 `crypto_weekend`: BTC and ETH quoted all weekend 2021-07-31/08-01 (2,870 and 2,858 bars, all masked); the reviewed file writes SIZE, SEND and FILL for BKB's order 162767880003 (window Saturday 00:00-00:05 server); this file writes none, and every sleeve's paper lines and the 29 real positions equal the run without the weekend bars |
| F3 | major: the user's plan D2 could not be set | rates up to 10 %; `InpGuard` (15 inputs); defaults D2 = `0:10;3000:5;10000:2;20000:1`, `InpStopFallPct` 0 (no plan stop), `InpGuard` false; presets S7 and F3S in SPEC 1; the 20 x balance cap stays, now a release-guarded constant | T7a: D2 and S7 equal growth.run_one (schedules "D2", "S7") at the edges x1, x0 and x-0.5, taken, skips and weekly balances to the cent (T7a below); T7b: D2 equals growth.engine (5,190 requests, 4,862 taken, 0 per-trade differences); the margin reading at 1:2 (T7b below); 366 golden vectors with the D2 and S7 tables; test_release: 15 inputs with D2's defaults |
| F4 | minor: the entry blocks were read only at the first sizing | the blocks (STOPPED, GUARD, LOCK, FRIDAY, CLOCK, self-test, NOTRADE) and READY are read again just before every request | T8 `block_resend` (J): a BKB intent sized one minute before the Friday close, whose opens the broker refuses; the reviewed file keeps sending after the close and opens it inside the Friday window (the Friday close closes it a second later); this file stops at the close (4 refusals before it), opens nothing and writes `MISSED reason=friday` |
| F5 | minor: T6 counted EA decisions against the paper as explained | T6 reports entries delayed by a start, exits in a start and EA-initiated closes apart; the last fail against an open paper trade | as F1 |
| F6 | minor: the two shadow journals differ by design | an observer makes its market intents at activation (sized NOTRADE, never sent), as the VPS copy with `InpTrade` false does; SPEC 10.2 and 10.12 written step by step | T8 `shadow`: one week of 2021, the observer's and the VPS copy's SIZE, MISSED, DEC and paper lines (2,619 each, 37 live SIZE lines) are identical; on the reviewed file they differ |
| F7 | minor: GFP skipped every Friday of a gold session ending before 16:55, silently | a session (or the time before a known closure) reaching 16:46 New York is enough; a Friday skipped for the session is pushed (live only) | T8 `gfp_session`: a session ending 16:50 New York: GFP trades (the reviewed file skips it); ending 16:40: one DEC skip line (reason 4) and one push (the reviewed file: no push) |
| F8 | minor: only SL > 0 checked for NOT_READY positions | a position with no expected stop whose stop fresh quotes have shown crossed for 2 min is closed (`SLFIX why=wrong_side`) | T8 `wrong_side` (J, new mock fault `sl_stuck`): the reviewed file keeps the position to its `LatestExit` 9.4 h later; this file closes it 122 s after the stop went wrong |
| F9 | minor: every journal line Printed and flushed | `rp=1` lines go to the file only; one flush per timer pass | test_release, one week of 2021 in the release build: 2,883 lines in the file, 2,420 with `rp=1`; 463 Printed, none with `rp=1`; 207 flushes for 7,200 timer passes (one per line before) |
| F10 | minor: two copies could trade one demo account around a migration | SPEC 10.15: the migration step by step (MetaTrader turns local automated trading off at a migration, MT5 help "Migration"; the Mac's Algo Trading off first, `InpTrade` true while migrating, then false on the Mac) | procedure; nothing to run here |
| F11 | minor: margin never binds in the mock | T7b reading with crypto at 1:2, run with T7b by default (never a pass condition) | T7b below: D2 462 and S7 250 MARGIN skips, the EA equal to growth.engine at the same leverage |
| F12 | minor: the MetaEditor compile cannot be proven here | none | still SPEC 10.1, the gate before any trading |
| X1 | step K's request 5: the 20 gold bars of 2012-12-31 17:00-17:58 New York | `export_frames.py` drops gold bars of 17:00-17:59 New York; the references were rebuilt; T2 and test_GFP fail if such a bar comes back | the gold frame has 3,172,965 bars (20 fewer); the mask drops no in-sample bar; the GFP January 2013 differences are gone (T4 below). T2's new check of the export's filter on the lab frame of 2012-12-31 (20 bars of 17:00-17:58 New York there, none exported) fails with the reviewed commit's `export_frames.py`, which exports all 20 |
| K1 | step K's request 1: a CR_NO_GUARD build warned | the `settled` variable moved | 0 warnings in every build, CR_NO_GUARD builds included (test_release, test_account, test_t7b) |

## 1. What changed

### The fix round after the review (this report)

- `src/CR_Rule_F1.mqh`: `F1H2Horizon(t_dec)` (H2's horizon, shared by the order and `LatestExit`); with H2 on,
  `LatestExit` is that horizon (F1).
- `src/CR_Bars.mqh`: the time of the first READY check of each load, `BarsNotReadyFor` (F1) and `BarsShut` (a minute
  masked for the symbol or inside a known closure, F2).
- `src/CR_Follower.mqh`: NOT_READY exits only after the first READY check and 10 min of NOT_READY (F1); no activation and
  no request in a shut minute (F2); the entry blocks and READY again just before every request (F4); an observer makes
  its market intents at activation (F6); a position with no expected stop whose stop fresh quotes show crossed for 2 min is
  closed (F8).
- `src/CR_Main.mqh`: the READY checks before the follower in every pass (F1); `InpGuard` into the configuration (F3); the
  replay flag for the rules (F7); one journal flush per timer pass (F9); the release guard of the 20 x balance cap.
- `src/CR_Journal.mqh`: `rp=1` lines to the file only, `JrnFlush` (F9).
- `src/CR_Rule_GoldFri.mqh`: a session or a known closure reaching 16:46 New York; the push of a Friday skipped for the
  session (F7).
- `src/CR_Sizing.mqh` (rates up to 10 %), `src/CR_Ledger.mqh` (`InpStopFallPct` 0 = no plan stop; GUARD (b) and (c) only
  with `InpGuard` true), `src/CR_Guards.mqh` (GUARD (a) and the mark only with `InpGuard` true; the `settled` warning),
  `src/CR_Types.mqh` (`guard_off`), `src/ClaudeRobot.mq5` (15 inputs, D2's defaults), `src/CR_Broker.mqh`
  (`CR_BRK_NOTIONAL_X` under `#ifndef`, refused by the release self-test unless 20): F3.
- `tools/gen_golden.py`, `src/CR_Golden.mqh`: the D2 and S7 tables, 15 keys: 366 vectors (F3).
- `check/export_frames.py`: gold bars of 17:00-17:59 New York dropped; the in-sample bars, frames and `ref_lab.py`
  references rebuilt (X1).
- `check/mock_replay.h` (a flush counter on the summary line; positions whose stop the broker does not execute),
  `check/mock_faults.h` (fault `sl_stuck MAGIC PRICE`), `check/run_tests.py` (`--jobs N`: tests side by side, the longest
  first).
- Tests: `test_restarts.py` (check 4 and the start-up split, F1 and F5; the F3S preset explicit; after the first
  suite run, an ORPHAN class and the end of a start-up window, section 3 T6), `test_F1.py` (`LatestExit` with H2 on,
  48 unit cases), `test_GFP.py` (the 16:46 limit in its session and closure unit cases), `test_worlds_rules.py`
  (worlds `h2_restart`, `notready_gate`, `crypto_weekend`, `shadow`, `gfp_session`), `test_worlds.py` (worlds
  `wrong_side`, `block_resend`; the F3S preset explicit, since SPEC 1's defaults are D2 now), `test_account.py` and
  `test_account.cpp` (D2 and S7 against growth.run_one, the engine copy for plain schedules, unit worlds for 10 %, D2, S7
  and no plan stop), `test_t7b.py` (D2, the readings, the 20 x cap raised and counted, the plan inputs explicit),
  `test_exec.cpp` (`InpGuard` false), `test_golden.cpp` (5 tables), `test_release.py` (15 inputs, D2's defaults, the
  journal checks, the notional guard), `test_accept.py` (the golden count read from `CR_Golden.mqh`).
- After the machine restarts (the last round of this report): `test_bars.py` (the mask may drop no in-sample bar at all,
  and the export's own filter is checked on the lab frame of 2012-12-31), `test_GFP.py` (the rebuilt frame must be the
  kept frame), both so that the 20 gold bars of X1 fail the suite if they come back; `test_t7b.py` (the 1:2 margin
  readings run by default, never a pass condition, so that the suite's run gives them on the final tree).
- `SPEC.md` v2.1: sections 1, 2.2, 2.6, 3 (H2, GFP), 4.1, 4.4, 4.8, 4.9, 5, 6.1, 6.2, 7 (T2, T6, T7a, T7b, T8, T10), 9
  (items 10, 16, 17), 10 (items 2, 5, 6, 12, 13 and the new 15) and one row per finding in section 11.

### Step K (the edition the review read)

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

Every run below is on the dist file `1cf1d0cab64b` (`src/` unchanged since the first one).
- First run, `check/run_tests.py --jobs 3` (three tests at once on four cores), 2026-11-13 22:59 to 2026-11-14 00:00 UTC:
  29 of 31. Both failures were in the tests: test_GFP's session cases still expected the old 16:55 limit (corrected
  after that run had started), and T6 had no class for one legitimate ORPHAN (section 3, T6). With both corrected, T6's
  saved data passed (`--analyse`) and test_GFP passed alone.
- Second run, `--jobs 3`, from 00:04: cut short by a machine restart after two tests (the disk allowance was full at the
  time; 9 GB of old scratch files have since been deleted, and this run kept about 10.9 GB free throughout).
- The run reported here, after this round's test changes (section 1): `check/run_tests.py` with its default `--jobs 1`,
  one test after the other, 2026-11-14 00:39:36 to 2026-11-14 02:49:27 UTC: 31 of 31. The table is that run (`check/out/tests/summary.json`, one log per test beside
  it; the runner's own log `check/out/fix/suite_final.log`). Times are wall-clock; several tests run more than one
  process. Every binary was compiled afresh in this run (`build/` was emptied before it, and every build starts from
  an empty folder). Some rule tests (N30, OC4, NQB, GFP, D4H, and some sanitizer replays) reused journals replayed
  earlier by a byte-identical binary on the same bar files: their keys hold the sha256 of the compiled binary, the inputs
  and the bar files' sizes and times, so a reused journal is the one this binary writes; the replay times such a test
  prints are those measured when the journal was made.

| SPEC 7 | Test | Step | What it checks | Result | Wall time |
|---|---|---|---|---|---|
| S0 | `test_s0_build.py` | S0 | the dist file and every variant build with 0 warnings; the translator refuses the banned constructs | pass | 88 s |
| S0 | `test_s0_dbl.py` | S0 | the clock double equals zoneinfo, every hour 2012-2035 | pass | 7 s |
| S0 | `test_s0_refs.py` | S0 | ref_lab.py gives the official in-sample trades of the ten sleeves; the change references | pass | 9 s |
| S0 | `test_s0_replay.py` | S0 | the driver replays 2021 on the four symbols, journal parsable (InpTrade false) | pass | 95 s |
| S0 | `test_s0_script.py` | S0 | CR_Rule_Script replays the lab's orders field by field | pass | 20 s |
| T1 | `test_clock.cpp` | A | hand cases from SPEC 2.1; the evaluator test_clock.py drives | pass | 16 s |
| T1 | `test_clock.py` | A | clocks, NYSE calendar, closures, parser, exit minutes against the lab | pass | 57 s |
| T2 | `test_bars.cpp` | B | mock worlds: barrier, holes, late bars, READY, mask | pass | 42 s |
| T2 | `test_bars.py` | B | bars, mask, quotes, aggregates, primitives against pandas and the lab; no in-sample bar masked and the export's gold filter (new) | pass | 135 s |
| T3 | `test_paper.cpp` | C | paper unit worlds | pass | 20 s |
| T3 | `test_paper.py` | C | random orders against gl.simulate; end to end on the lab's orders; broken engines caught | pass | 332 s |
| T4 | `test_N30.py` | D | N30 decisions and trades against the lab; holes and restarts worlds | pass | 45 s |
| T4 | `test_OC4.py` | D | OC4 likewise | pass | 6 s |
| T4 | `test_BK.py` | E | BKB and BKE against the lab | pass | 70 s |
| T4 | `test_F1.py` | E | F1B and F1E against the lab; the frozen scorecard; LatestExit with and without H2 (new) | pass | 14 s |
| T5 | `test_changes.py` | E | K1, S0.75r and H2 against the lab's own implementations | pass | 20 s |
| T4 | `test_NQB.py` | F | NQB decisions, trades and sigma; holes and restarts worlds | pass | 112 s |
| T4 | `test_GFP.py` | G | GFP decisions and trades against the lab; the 16:46 session and closure limit; rebuilt frame = kept frame (new) | pass | 72 s |
| T4 | `test_ORX.py` | G | ORX decisions and trades against the lab | pass | 51 s |
| T4 | `test_D4H.py` | H | D4H decisions, trades and ATR; holes, restarts and unit worlds | pass | 94 s |
| T4, T5 | `test_accept.py` | K | the shipped file, ten sleeves at once, switches off and on: the steps' journals and the lab | pass | 653 s |
| T6 | `test_restarts.py` | K | about 1,000 restarts and 10 outages per setting, switches off and on; no close the EA decides against an open paper trade (new) | pass | 2,744 s |
| T7a | `test_account.cpp` | I | ledger and sizing unit worlds (10 %, D2, S7, no plan stop, guard off: new) | pass | 8 s |
| T7a | `test_account.py` | I | ledger and sizing against growth.run_one: F3S, F2S, F1S, and D2, S7 (new), at three edges | pass | 1,401 s |
| T7b | `test_t7b.py` | K | the whole EA against growth.engine: F3S, F2S, F1S, F3S with the changes, and D2 (new); the 1:2 margin readings of D2 and S7 (new, not a pass condition) | pass | 508 s |
| T8 | `test_worlds.py` | J | execution layer on the lab's orders: 3 clean worlds, 32 fault worlds (wrong_side, block_resend: new), sanitizer | pass | 295 s |
| T8 | `test_worlds_rules.py` | K | the shipped file with the real rules: 5 clean worlds, 3 rule worlds, and the 5 worlds of the review's fixes (new) | pass | 635 s |
| T9 | `test_exec.cpp` | J | broker, guards and ledger worlds (InpGuard false: new) | pass | 29 s |
| T9 | `test_hands_port.py` | J | the 64 hands' tests SPEC 7 T9 keeps | pass | 39 s |
| T10 | `test_golden.cpp` | K | GoldenCheck on the shipped file (366 vectors); one changed vector of each kind refused | pass | 36 s |
| T10 | `test_release.py` | K | dist = amalgam(src); constants, the 15 inputs, subset; the release guards; the journal (new) | pass | 140 s |

31 of 31 pass; the whole run took 2.2 h (7,791 s).

## 3. Per test

### T1: clock (step A: `test_clock.cpp`, `test_clock.py`)

| Check | Count | Differences |
|---|---|---|
| UTC to server, New York, London and back; both summer-time flags; server day and week (every hour 2012-2035 and every minute within 3 h of the 96 switches) | 244,368 instants | 0 |
| NYSE full and half days against `us_holidays` (2000-2040) | 14,976 dates (383 full, 88 half) | 0 |
| BusinessDays against pandas BDay | 359,424 queries | 0 |
| AddTradingDays against `trend.add_trading_days` (all in-sample gold 4h closes, and every 30 min of 2012-2035 for 8 values of n) | 14,397 closes; 8 x 420,768 grid instants | 0 |
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
| The mask (SPEC 2.2, after the B1 decision): bars dropped in sample | 0 (the 20 gold bars of 2012-12-31 17:00-17:58 New York that step K's mask dropped are no longer exported, X1); any dropped bar now fails T2 | equal to an independent pandas mask |
| `export_frames.py`'s gold filter on the lab frame of 2012-12-31 (new, X1) | 1,279 lab bars, 20 of them 17:00-17:58 New York; 1,259 exported | none of the 20 exported, every other bar kept (with the reviewed commit's `export_frames.py`: all 20 exported, the check fails) |
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
3. **The sanitizer build** replays both settings with a byte-identical journal (299 s switches off, 287 s on).

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
| GFP | 1,304 / 1,304 | 416 | 417 | 416 | 416 / 416 / 416 | the 2013-05-31 hole day (below); the January 2013 stops of step K are gone (X1) |
| D4H | 29,279 / 29,279 | 494 | 494 | 494 | 494 / 494 / 494 | one lab trade open at the frame end, left out |
| ORX | 3,906 / 3,906 | 1,038 | 1,038 | 1,038 | 1,038 / 1,038 / 1,038 | one lab trade open at the frame end, left out |

Step K's list had a second GFP difference against the rebuilt frame, three January 2013 stops (one 5.8e-10 relative):
the rebuilt frame kept 20 gold bars of 2012-12-31 17:00-17:58 New York that the EA masks, and they seeded the lab's
Wilder hour ATR. `check/export_frames.py` now drops gold bars of 17:00-17:59 New York (X1), so the rebuilt frame holds
exactly the kept bars, and the lab on them gives the same trades as the lab on the EA's kept bars (test_accept checks both).
test_GFP now also fails if the mask drops any bar of the export (the rebuilt frame must be the kept frame: 3,172,965 bars
each, 0 dropped), and T2 fails on any in-sample bar the mask drops.

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
3. **D4H and ORX: one lab trade each still open at the frame end** (its exit falls in 2022): left out (SPEC 7).
4. **EA orders the lab drops** (no trade results): BKB 29, BKE 19 (18 with K1), F1B 3, F1E 3, NQB 5 orders whose window
   has no kept bar within 5 minutes (the lab's make_orders drops them by looking ahead; the paper lets them expire). GFP 0.

Against the official trades (`results/r2/recalc`, the lab's own frames, not the robot): the export rounds the bid to 2
digits (SPEC 7), which moves razor decisions: N30 1 trade (2019-05-23), OC4 1 stop exit (2018-03-05), BKE 1, F1E 2 (+1
added), NQB 1 (2018-05-25: 6.0026 against 5.9994 sigma), D4H 8 of 495; prices otherwise within 0.014 USD. FP's real
digits (SPEC 10.3, 10.6) settle this.

### T6: restarts and outages (K: `test_restarts.py`)

The shipped file (harness build) trades on a demo account in the mock over the whole in-sample period (2013-2021, the
four symbols): 100,000 EUR, the F3S preset set explicitly (SPEC 1's defaults are D2 now; T6 checks the follower, not the
plan), `InpPlanStart` before the data. For each switch setting (off, and on with the K1 folds of T5) one continuous run
is the reference. The same period is then cut into about 1,000 processes. Each new process starts from the mock's saved
broker state (positions, orders, deals, balance) and nothing else: the EA rebuilds its bars from the depth only (120 days
of gold, 60 of the others) and its state from the broker. The restart points come from the continuous run, for each
sleeve: 50 inside its open paper trades, 30 one to ten minutes before one of its decisions, 20 at random weekday minutes;
points closer than 10 minutes are merged. Ten restarts are outages: the next process starts 1 to 6 hours later, while the
broker's stops keep working. The points are the same as in step K's run (same seeds, same paper trades).

| Setting | Restarts (in trades / before decisions / random) | Outages | Processes: SELFTEST ok, one REBUILD, no ERROR | Rebuild from the depth only | Wall time |
|---|---|---|---|---|---|
| off | 995 (499 / 296 / 200), 2013-01-11 to 2021-12-28 | 10, 1.08 to 5.38 h | all 996 | yes: 17,046 to 172,860 minutes | 568 s continuous, 2,160 s restarted |
| on | 987 (494 / 295 / 198), 2013-01-04 to 2021-12-31 | 10, 2.4 to 5.87 h | all 988 | yes: 6,233 to 172,860 minutes | 557 s continuous, 2,083 s restarted |

**Check 1, the later paper trades.** Every paper trade that ends after the first restart is compared with the
continuous run's trade of the same order id: fill time, bar, price, side and first stop; exit event, time, price and
reason. A trade is taken from the first process that finishes it (a later process only replays it). An exit can be
written after its time (a PREVISE 30 minutes after a weekend, or an exit bar whose barrier falls in the next process), so
a process may finish trades whose exit lies up to 4 days before its start. Switches off: 7,962 trades, 7,958 bit for bit,
4 within 1e-12; switches on: 7,840 trades, 7,836 bit for bit, 4 within 1e-12; none missing, extra or different. Each
cell: switches off / on.

| Sleeve | Trades checked | Bit for bit | Within 1e-12 | Missing, extra, different | Restarts inside its open trades | Restarts 1-10 min before its decisions | Outages over its trades |
|---|---|---|---|---|---|---|---|
| N30 | 1,642 / 1,642 | 1,642 / 1,642 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 166 / 139 | 41 / 43 | 5 / 4 |
| OC4 | 999 / 999 | 999 / 999 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 173 / 196 | 36 / 35 | 4 / 5 |
| BKB | 645 / 664 | 645 / 664 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 371 / 338 | 79 / 87 | 2 / 5 |
| BKE | 519 / 428 | 519 / 428 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 333 / 267 | 80 / 67 | 3 / 3 |
| F1B | 631 / 631 | 631 / 631 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 267 / 248 | 57 / 63 | 4 / 4 |
| F1E | 518 / 465 | 518 / 465 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 231 / 293 | 52 / 57 | 2 / 3 |
| NQB | 1,063 / 1,063 | 1,059 / 1,059 | 4 (at most 2.2e-16) / 4 (at most 2.2e-16) | 0, 0, 0 / 0, 0, 0 | 99 / 97 | 57 / 56 | 1 / 2 |
| GFP | 417 / 417 | 417 / 417 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 78 / 76 | 31 / 30 | 2 / 2 |
| D4H | 494 / 494 | 494 / 494 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 295 / 286 | 97 / 81 | 3 / 3 |
| ORX | 1,034 / 1,037 | 1,034 / 1,037 | 0 / 0 | 0, 0, 0 / 0, 0, 0 | 624 / 623 | 33 / 34 | 7 / 7 |

The 4 NQB trades per setting (stop and exit within 2.2e-16): after a start, the rolling sums of NQB's sigma begin at
another minute, so their last bits differ (section 4, item 1).

**Check 2, every process:** SELFTEST ok, exactly one REBUILD, from the depth only, and no ERROR (996 and 988 processes).

**Check 3, the real positions (SPEC 4.8).** The real trades of the restarted run are matched with the continuous run's by
sleeve, side and entry time. Every difference has a cause, and none is left unexplained. Since the review (F5) the
start-up differences are reported apart:
- *entry delayed by a start* and *exit in a start*: the entry or exit falls in a start-up window, from the restart to two
  minutes after the start's first live barrier, or after its last reconcile within an hour of that barrier, whichever is
  later. The median window is 8 minutes. A restart inside a weekend, holiday or daily closure goes live when the markets
  reopen, up to 75 hours later (17 windows off and 31 on last over an hour; each starts in a weekend, a holiday or a daily
  closure, or a few minutes before one, when no market of the robot has bars).
- *outage*: the entry or exit falls while the EA was down.
- *lots only*: entry and exit times and prices are equal; only the lots differ. After the first trade that differed
  (2013-07-18 off, 2013-06-26 on) the shared account's balance differs, so later lots differ: restarted / continuous lots
  have a median of 0.989 off and 0.979 on; 90 % lie between 0.975 and 1.014 off, between 0.953 and 1.005 on. The
  extremes, 0.24 and 4.10, come from the stake rule's cushion factor m (between 0.25 and 1, `SizM`): from 100,000 EUR the
  risk rung never moves, so only m can change a lot fourfold.
- *sizing skip*: one run skipped the intent because its caps were full (switches on: N30 1, OC4 1, GFP 1), again after an
  earlier difference.

Each cell: switches off / on.

| Sleeve | Continuous | Restarted | Identical | Entry delayed by a start | Exit in a start | In an outage | Lots only (balance path) | Sizing skip in one run | EA closes against an open paper trade | Unexplained | Most open at once |
|---|---|---|---|---|---|---|---|---|---|---|---|
| N30 | 1,590 / 1,593 | 1,580 / 1,585 | 633 / 783 | 45 / 33 | 10 / 6 | 3 / 4 | 918 / 781 | 0 / 1 | 0 / 0 | 0 / 0 | 1 / 1 |
| OC4 | 988 / 989 | 983 / 985 | 472 / 580 | 30 / 28 | 5 / 2 | 1 / 1 | 493 / 390 | 0 / 1 | 0 / 0 | 0 / 0 | 1 / 1 |
| BKB | 621 / 638 | 621 / 634 | 39 / 39 | 10 / 16 | 2 / 1 | 0 / 1 | 575 / 587 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| BKE | 496 / 405 | 495 / 402 | 436 / 359 | 8 / 12 | 1 / 1 | 1 / 1 | 54 / 37 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| F1B | 616 / 616 | 615 / 610 | 66 / 73 | 10 / 16 | 1 / 2 | 1 / 2 | 543 / 529 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| F1E | 507 / 456 | 507 / 453 | 468 / 409 | 16 / 19 | 2 / 0 | 0 / 0 | 29 / 36 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| NQB | 807 / 818 | 804 / 809 | 117 / 116 | 21 / 20 | 3 / 9 | 0 / 4 | 675 / 676 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| GFP | 336 / 336 | 336 / 334 | 116 / 98 | 6 / 3 | 3 / 0 | 0 / 2 | 214 / 234 | 0 / 1 | 0 / 0 | 0 / 0 | 1 / 1 |
| D4H | 471 / 471 | 469 / 471 | 171 / 147 | 4 / 0 | 0 / 0 | 0 / 0 | 297 / 324 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| ORX | 1,004 / 1,004 | 1,004 / 1,003 | 269 / 268 | 6 / 7 | 1 / 2 | 0 / 0 | 731 / 730 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 1 |
| all | 7,436 / 7,326 | 7,414 / 7,286 | 2,787 / 2,872 |  |  |  |  |  | 0 / 0 | 0 / 0 |  |

With the switches on, 2,872 real trades are now identical, against 2,489 in step K's run: F1E alone went from 356 to
409, because its held positions are no longer closed at a restart.

**Check 4, closes the EA itself decides in a start-up window (new: review F1 and F5).** A `CLOSE why=latest_exit` or
`why=orphan` inside a start-up window, of a position whose paper trade (the continuous run's trade of that sleeve and
side, filled within 5 minutes of the real entry) is still open at that moment, fails the test.

| | This file, off | This file, on | Reviewed file, off | Reviewed file, on |
|---|---|---|---|---|
| EA closes in start-up windows | 20 (all `orphan`) | 9 (all `orphan`) | 31 (25 `latest_exit`, 6 `orphan`) | 78 (77 `latest_exit`, 1 `orphan`) |
| ... of them against an open paper trade | 0 | 0 | 1 (ORX 1) | 55 (F1E 53, ORX 2) |
| Check 4 | pass | pass | fails | fails |

The reviewed file's column is its own T6 data (saved before this suite replaced it, `check/out/fix/t6_reviewed_file_*`),
read by the same checks (`build/fix/t6_reviewed.py`, `check/out/fix/t6_reviewed_file_new_check.json`): the 53 F1E
closes are the review's 53 held F1E+H2 trades; the 3 ORX closes are an exit inside the Presidents' Day 2020 and the Good
Friday 2018 gold closures and one after a data hole. This file closes nothing at `LatestExit` in any start-up window.

Never two positions of one sleeve at once, and no DUP. The follower's lines over all processes:

| | Switches off | Switches on |
|---|---|---|
| ADOPT | 2,484 | 2,401 |
| ORPHAN: after an outage / its paper trade ended during the start-up / it ended before the restart, the close still waiting for the market / other | 8 / 16 / 0 / 0 | 5 / 18 / 1 / 0 |
| DUP, SLFIX, REFUSED | 0, 0, 0 | 0, 0, 0 |
| MISSED: late (the paper trade opened while the EA was down or starting, past its 5-minute window) / cap / exited | 36 / 66 / 1 | 56 / 59 / 1 |
| Robot positions open across a restart: adopted or closed by the next process / closed by their own broker stop before the reconcile / neither | 2,508 / 14 / 0 | 2,425 / 8 / 0 |

There are more ORPHANs than in step K's run (6 and 3 then): a position whose paper trade ended while the EA was starting
used to be closed at `LatestExit` by the NOT_READY exits before the reconcile; now the reconcile decides first (SPEC 4.8)
and closes it as ORPHAN. The first run of this suite failed T6 on one of them, a class the test did not have: process
837 (switches on) restarted at 2021-01-01 00:53 UTC; BKB's paper trade 160944840003 had ended at 00:00 (time exit) inside
the crypto New Year closure, so the continuous run's close waited for the reopening (Sunday 2021-01-03 22:00:02 UTC).
The new process went live at the reopening and closed the position as ORPHAN at its first reconcile, 22:06:02, six
minutes after the continuous run. ORPHAN is the right decision there: the paper trade is over. Check 3 now accepts an
ORPHAN whose paper trade ended before the restart while the continuous run's close was still waiting, and the start-up
window runs to the last reconcile within an hour of the first live barrier, not of the restart (a restart inside a
closure reconciles only when the market reopens; the window only grows, so check 4 sees more closes, not fewer). The
saved data passed with these two changes (`--analyse`), and so did the suite run of section 2.

### T7a: ledger and sizing against growth.run_one (step I: `test_account.cpp`, `test_account.py`)

The official in-sample trades of the ten sleeves (entries 2018-02-01 to 2021-12-31, 5,207 trades, 207 weeks), 1,000 EUR
at the start and each month (46 payments), through I's own driver and the mock broker, against growth.run_one on
`growth.arrays(price_level="is")`, at the lab's edges x1, x0 and x-0.5. F3S, F2S and F1S run with their plan stop and
`CR_NO_GUARD`, as before. D2 and S7 (new) run with no plan stop (`InpStopFallPct` 0) and `InpGuard` false in the build
with the guard compiled in, against growth.py's schedules "D2" and "S7", which apply no stop (the engine only records the
week its -50 % rule would have fired; the EA, without guard, ignores it, as the user chose).

Every count below is the same for the EA and the lab:

| Plan, edge | Taken | Minimum lot | Caps | After the plan stop | Stop week | Final balance (EUR) | Weekly balance, largest difference |
|---|---|---|---|---|---|---|---|
| D2 x1 | 4,878 | 0 | 329 | no plan stop | none | 4,550,059.46 | 0 EUR |
| S7 x1 | 4,878 | 0 | 329 | no plan stop | none | 1,169,177.89 | 0 EUR |
| F3S x1 | 4,876 | 3 | 328 | 0 | none | 358,838.34 | 0 EUR |
| F2S x1 | 4,873 | 5 | 329 | 0 | none | 357,574.41 | 0 EUR |
| F1S x1 | 4,860 | 19 | 328 | 0 | none | 319,480.88 | 0 EUR |
| D2 x0 | 4,878 | 0 | 329 | no plan stop | none (the -50 % rule would fire in week 5) | 16,410.43 | 0 EUR |
| S7 x0 | 4,878 | 0 | 329 | no plan stop | none (week 5) | 24,533.50 | 0 EUR |
| F3S x0 | 4,266 | 2 | 293 | 646 | 183 | 36,837.66 | 0 EUR |
| F2S x0 | 4,263 | 5 | 293 | 646 | 183 | 36,525.37 | 0 EUR |
| F1S x0 | 4,218 | 18 | 293 | 678 | 182 | 37,578.00 | 0 EUR |
| D2 x-0.5 | 4,870 | 10 | 327 | no plan stop | none (week 3) | 6,466.91 | 0 EUR |
| S7 x-0.5 | 4,869 | 11 | 327 | no plan stop | none (week 5) | 10,126.42 | 0 EUR |
| F3S x-0.5 | 1,151 | 2 | 76 | 3,978 | 49 | 8,829.43 | 0 EUR |
| F2S x-0.5 | 1,147 | 6 | 76 | 3,978 | 49 | 8,827.73 | 0 EUR |
| F1S x-0.5 | 1,511 | 18 | 100 | 3,578 | 67 | 12,109.42 | 0 EUR |

Margin skips are 0 in every run (the mock's crypto margin is 1:50; T7b reads 1:2). Money paid in: 47,000 EUR in every
run without a stop. Per trade, lots, m, w, unit, B, P_in and rate are bit for bit equal to a recording copy of the engine,
now written for the plain schedules too (checked against run_one bit for bit). F3S and D2 at x1 and x-0.5 under the
sanitizer give the same; with each deposit's deal 45 s before the balance shows it (R16), 1,210 sizing waits and the same
result. Unit worlds: 339 checks in each of four builds (plain, sanitizer, each with and without `CR_NO_GUARD`), 0 failed;
new among them: 10 % accepted and 10.5 %, 11 % refused, D2 and S7 parsed and rated at every boundary (3,000, 10,000,
20,000) against growth._pct, `InpStopFallPct` 0 accepted as "no plan stop", and the fall that stops F3S leaves D2 trading
at 2 % (max(B 8,999, P_in 12,000) = 12,000).

What the table says to the user, in sample and with the official trades only (not a forecast): D2 and S7 take every
trade the caps allow from the first month (no minimum-lot skip at x1); at the edge x0 (rules that only cover their costs)
D2 ends at 16,410 EUR for 47,000 paid in and S7 at 24,534; at x-0.5, 6,467 and 10,126 EUR.

### T7b: the whole EA against growth.engine (K: `test_t7b.py`)

The shipped file (harness build with `CR_NO_GUARD`, SPEC 7) trades on a demo account in the mock from 2018-02-01 to
2021-12-31: all ten real rules, J's follower and broker, I's ledger and sizing. 1,000 EUR at the start (InpPlanStart =
the start) and 1,000 EUR on the first of each month (46 deposits, 47,000 EUR in all), fast mode, no broker commission on
gold (SPEC 1 and 7: the exported spread already holds the lab's commission). The plan inputs are explicit (F3S, F2S, F1S
with their stop; D2 with none). The lab's engine has neither a volume cap nor a cap on a position's value, so this
harness raises both (`MOCK_VMAX`, and `CR_BRK_NOTIONAL_X`, which every release build fixes at 20 and checks in its
self-test) and lists the requests they would cut.

The reference is growth.run_one, and I's recording copy of growth.engine (bit for bit the same, checked), fed the EA's
own trades and payments: one trade per sizing request of the EA (its SIZE line), with the stamp as entry time, the EA's
own close stamp from the deal (SPEC 5: a broker stop hit in minute X is booked at X + 60 s, an EA close at X), the paper
fill as entry price, the EA's sizing risk r of SPEC 4.2 (with a change on: r / f, the frozen stake factor), and the money
the account booked (side x (real exit - real entry)).

| Plan | Requests | Taken EA / lab | Minimum lot EA / lab | Caps EA / lab | Stop week | Weekly balance, largest difference | Lots differing | Final balance EA / lab (EUR) |
|---|---|---|---|---|---|---|---|---|
| D2 (new) | 5,190 | 4,862 / 4,862 | 0 / 0 | 328 / 328 | none (no plan stop) | 1.4e-9 EUR | 0 | 5,559,972.03 / 5,559,972.03 |
| F3S | 5,190 | 4,859 / 4,859 | 4 / 4 | 327 / 327 | none / none | 2.9e-11 EUR | 0 | 382,133.78 / 382,133.78 |
| F2S | 5,190 | 4,857 / 4,857 | 6 / 6 | 327 / 327 | none / none | 1.2e-10 EUR | 0 | 367,350.92 / 367,350.92 |
| F1S | 5,190 | 4,852 / 4,852 | 11 / 11 | 327 / 327 | none / none | 5.8e-11 EUR | 0 | 335,437.33 / 335,437.33 |
| F3S, switches on | 5,062 | 4,745 / 4,745 | 4 / 4 | 313 / 313 | none / none | 1.2e-10 EUR | 0 | 471,652.95 / 471,652.95 |

Money paid in by week: equal in every week (largest difference 0). The weekly balance differences come from the order in
which the two engines add the same amounts.

Listed, never silent (SPEC 7 T7b):
- **P1** (late gold intents sized on the larger of paper risk and quote risk, SPEC 4.2): the quote risk was larger on
  ORX 163, GFP 95 and D4H 87 requests (the largest ratio 1.30); the lots came out smaller on ORX 114, GFP 41 and D4H 60 of
  them under F3S (D2: 142, 65, 75). The reference is fed the EA's r, so these are listed, not differences.
- **P5** (`MISSED reason=exited`): 0 in this period.
- **NOT_READY**: ETH's data starts on 2018-01-01, so its 60-day depth (SPEC 2.2) is there only from 2018-03-02: BKE 8 and
  F1E 9 requests (7 with H2 on), left out of the reference.
- **Open at the end**: one ORX and one D4H position (opened 2021-12-31): kept as open positions (caps), booking nothing.
- **Volume cap**: a 100-lot SYMBOL_VOLUME_MAX would cut 52 BKE and 90 F1E orders late in the period under F3S, and 1,500
  requests under D2, whose balance reaches millions of EUR (N30 337, OC4 242, BKB 17, BKE 386, F1B 34, F1E 411, NQB 66,
  ORX 7); CR_Broker cuts them (`SEND cut=vmax`). FP's real caps are a Mac item (10.6).
- **The 20 x balance cap** (new): it would cut 10 D2 requests (N30 4, OC4 2, ORX 4), none under F3S, F2S or F1S. Run with
  the cap in force (an exploratory run before T7b raised it, `check/out/fix/t7b.log`), D2's first cut changes the
  balance path and every later lot (4,844 lots differ from the engine's), which is why T7b raises it; the release file
  keeps it.
- **Razor r**: for a distance stop the EA sizes on stop_dist, while the lab's trade risk is |entry - stop|; the two differ
  by rounding (about 1e-16 relative) on BKB 480, BKE 446, F1B 530, F1E 490, OC4 489 and NQB 929 trades; the reference is
  fed the EA's r, so none appears here.

**Reading (not a pass condition): D2 and S7 with the crypto margin at 1:2** (`MOCK_LEV_BTCUSD.r = MOCK_LEV_ETHUSD.r = 2`,
FP's retail crypto margin may be 50 %; review F11). The same runs as above, and growth.engine fed the same trades with the
same crypto leverage. Since this round they run with every T7b by default, so these numbers come from the suite run of
section 2 (`check/out/test_t7b/summary_readings.json`):

| | D2 at 1:2 | S7 at 1:2 |
|---|---|---|
| Requests | 5,190 | 5,190 |
| Taken, EA / lab | 4,484 / 4,484 | 4,654 / 4,654 |
| MARGIN skips, EA / lab | 462 / 462 | 250 / 250 |
| per sleeve (EA = lab) | N30 7, OC4 7, BKB 68, BKE 43, F1B 90, F1E 78, NQB 165, GFP 1, D4H 1, ORX 2 | N30 9, OC4 5, BKB 35, BKE 27, F1B 42, F1E 37, NQB 91, GFP 2, D4H 1, ORX 1 |
| Caps | 244 | 286 |
| Final balance (EUR) | 1,762,402.98 (5,559,972.03 at 1:50) | 903,500.23 |

At 1:2 a crypto position ties up half its value, so the margin binds once the open crypto positions are large against the
balance: most skips are crypto trades (NQB, F1B, F1E, BKB, BKE), and a few US100 and gold trades meet the margin those
positions hold. The EA and the engine skip exactly the same trades. FP's real margin rates are a Mac item (10.6).

### T8: broker faults and clean worlds (J: `test_worlds.py` with script sleeves; K: `test_worlds_rules.py` with the real rules)

J's 32 fault worlds and 3 clean worlds run the ten sleeves on `CR_Rule_Script` (the lab's own orders replayed), so they
test the execution layer alone. Since SPEC 1's defaults are D2 now, they set the F3S preset explicitly (the plan they
were written for). 36 of 36 pass (the sanitizer world included), builds with 0 warnings (plain, h = 6, release,
sanitizer):
- clean_fast (2021): 1,437 live paper trades, 1,348 real positions at exactly the expected entry and exit prices (market
  slippage and stop slippage on the grid stop included), 89 sizing skips because the caps were full; paper = lab for all
  1,437 trades;
- clean_tick: the same 1,348 trades, 925 exits at the exact price, the 423 broker-stop exits at the triggering tick;
- clean_h (gold with h = 3 points): GFP 39, D4H 57 and ORX 126 closed trades, all exact (one D4H and one ORX position
  still open at the end);
- the fault worlds of SPEC 7 T8: refused stop or modify, a modify inside the freeze level, requote and timeout, a slow
  reply, a duplicate made by the broker, an N30 reversal close retried, a deal stamped after the terminal's clock, stops
  dropped by the broker or by hand, positions listed late after a restart, a restart mid-trade, a late bar, a hole that
  stays, rewritten comments with a NOT_READY sleeve, magic-0 deals, the clock 1 h off, deposits and withdrawals, the
  balance and history out of step for 30 s and 90 s, plan start unset, in the future and after manual losses, the plan
  stop, the guard (a, b, c and the mark refused while the market is closed), the daily lock, the Friday close, InpTrade
  false on the VPS, an observer off the VPS, a second and a crashed instance, P5, P4, Good Friday, the switches on demo
  and on real, the tester mode; new: a stop the broker moves to the wrong side of a NOT_READY sleeve's position
  (`wrong_side`, F8) and opens refused into the Friday close (`block_resend`, F4);
- the sanitizer world (Q1 2021, and two fault worlds again): identical output.

K runs the shipped file with the real rules (`InpScript` empty) in J's own harness, judged by J's own functions
(`real_vs_paper`, `lab_check`, `judge_clean`), over 2021 (the bars before 2021 are the first start's history). 13 of 13
worlds pass, builds with 0 warnings (plain, h = 6, sanitizer):

| World | What | Result |
|---|---|---|
| clean_fast | fast mode, switches off | 1,437 live paper trades: 1,348 real positions, every entry and exit at the expected minute and price; 89 sizing skips (caps full); paper = lab on all 1,437 (bit for bit, except NQB: 3 stops and 1 exit within 1.9e-16 relative, section 4 item 1) |
| clean_on | switches on (K1, H2, S0.75r) | 1,380 live paper trades: 1,298 real positions exact, 82 sizing skips; BKB+S0.75r 151, BKE+K1 95 and F1E+H2 124 trades = ref_changes.py's chains, the seven others = ref_lab.py (NQB as in clean_fast) |
| clean_tick | tick mode (ticks open, low, high, close) | the same 1,348 positions; all entries exact; 925 exits exact, the stop exits at the triggering tick (the mock's model) |
| clean_h | gold with h = 3 points (`CR_XAU_COMM_PTS=6`, raw bid = lab bid + 3 points) | GFP 39, D4H 57, ORX 126 positions: entries and exits exact, the broker stop = paper stop + side x h triggers in the same bar |
| clean_san | the sanitizer build replays clean_fast | journal and deals identical (412 s) |
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
(section 4, item 6) is counted as exact at that open.

The worlds of the review's fixes (new in this round). Each fails on the reviewed file (CR_BUILD `1ca53085c0c1`,
commit ec43431, run by `build/fix/old_code_worlds.py` from a read-only `git show` of it) and passes on this one:

| World | Test | What | Reviewed file | This file |
|---|---|---|---|---|
| `h2_restart` (F1) | test_worlds_rules | switches on, one restart at 2018-03-16 08:29 UTC during the F1E trade oid 152102160006, held by H2 to 19:55 UTC | `CLOSE why=latest_exit` at 08:29:06 UTC, 11.4 h before the paper exit | adopted at the reconcile, closed at 19:55:02 UTC like the continuous run; no `latest_exit` close |
| `notready_gate` (F1) | test_worlds_rules | a restart at 14:55 New York on Presidents' Day 2020 during the ORX trade oid 158158806010 (its exit falls in the gold holiday closure), gold not synchronized for 5 min, then for 30 min | closed (`latest_exit`) 2 s before the first READY check | 5 min: nothing closed while NOT_READY, adopted when READY, closed at the reopening (23:00:02 UTC) like the continuous run; 30 min: the `LatestExit` close exactly 600 s after the first READY check |
| `crypto_weekend` (F2) | test_worlds_rules | BTC and ETH quoted all weekend 2021-07-31/08-01 (2,870 and 2,858 bars copied from the Friday) | SIZE, SEND and FILL of BKB's order 162767880003 (window Saturday 00:00-00:05 server) | the bars all masked, no crypto SIZE, SEND or FILL in the weekend; every sleeve's paper lines and the 29 real positions equal the run without the weekend bars |
| `shadow` (F6) | test_worlds_rules | one week of March 2021 run by the observer (off the VPS, demo, `InpTrade` false) and by the VPS copy with `InpTrade` false | the two journals differ | SIZE, MISSED, DEC and paper lines identical (2,619 each; 37 live SIZE lines, all `skip=notrade`); no SEND |
| `gfp_session` (F7) | test_worlds_rules | the broker's Friday gold session ending at 16:50 New York, then at 16:40 (mock fault `session`) | 16:50: the Friday skipped; 16:40: skipped without a push | 16:50: GFP's order as without session information; 16:40: one DEC skip line (reason 4, end 23:40 server) and one push |
| `wrong_side` (F8) | test_worlds | a restart while a BKB position is open, BTC never synchronized; the broker moves the stop to the wrong side and stops executing it (new mock fault `sl_stuck`) | kept to its `LatestExit` 9.4 h later | `SLFIX why=wrong_side` and the close about 2 min after the stop went wrong; pushed |
| `block_resend` (F4) | test_worlds | a BKB intent sized one minute before the Friday close (`InpFridayCloseHHMM`), its opens refused (requote) into the Friday window | opened inside the Friday window (then closed by the Friday close) | nothing opened; `MISSED reason=friday` |

### T9: the hands' tests ported (J: `test_exec.cpp`, `test_hands_port.py`)

- `test_exec.cpp`: 152 checks of the broker, guards and ledger worlds (sanitizer build), 0 failed; built with the sizing
  ports as `test_hands_port.py` builds it (`-DCR_EXEC_SIZING`, plain and sanitizer), 162 checks, 0 failed. New
  among them (F3): with `InpGuard` false the same fall to 50 % of ref latches nothing, closes nothing and marks nothing,
  and a mark in the history latches GUARD (c) only with `InpGuard` true.
- `test_hands_port.py`: the 64 hands' tests that SPEC 7 T9 names and the hands define (X5 does not exist in
  `test_mains.py`) pass in the plain and the sanitizer build, with identical output; where SPEC changed the hands'
  behaviour (M1, X9, K7, K8, K15, X10, O26, X8) the expected values follow SPEC and each line says so.

### T10: golden vectors and the release guard (K: `test_golden.cpp`, `test_release.py`, `tools/gen_golden.py`)

`tools/gen_golden.py` computes every vector with the lab's own code and writes `src/CR_Golden.mqh` (`--check` confirms
the file is its output). `GoldenCheck` runs at OnInit after the build-constant check; a mismatch blocks trading
(`SELFTEST ok=0`, every intent skipped as `selftest`).

| Vectors (366) | From | Compared |
|---|---|---|
| 60 clock instants (one second around the US and UK switches of 2012-2035, the gap weeks, ordinary times) | zoneinfo; `pont.server_to_utc` | server, New York and London clocks, the server clock back to UTC (the repeated autumn hour included), both summer-time flags: exact |
| 40 NYSE dates (2013-2033: full closures, 13:00 half days, open days, 2018-12-05 and 2025-01-09) | `idxus_lib.us_holidays` | exact; the rules only (`ClkHolKind`), so a typed InpExtraClosures entry cannot fail the self-test |
| 20 AddTradingDays | `trend.add_trading_days` | exact |
| 20 BusinessDays and 10 ORX time exits | pandas BDay, zoneinfo | exact |
| 30 F1 scores (24 lab candidates from the in-sample BTC and ETH frames, 6 made-up clip and dummy edges) | `ml/strategy.py` `score_model` | 1e-12 relative (the expected value is the in-order sum; numpy agrees within 1e-12) |
| 10 K1 riskbp of the lab's brk72 ETH orders | `s1_run.py:105` formula | 1e-12 relative |
| 5 risk tables (F3S, F2S, F1S, and new: D2, the default, and S7) at 15 keys (new keys 9,999.99, 10,000, 19,999.99, 20,000) | `growth._pct`, `growth.SCHEDULES` | exact; the live table is put back |
| a 48-value Wilder series and SMA series (with NaNs) | pandas `ewm(alpha=1/14, adjust=False)`, `rolling(14, 9)` | 1e-12 relative, NaN at the same places |

`test_golden.cpp` (the shipped file, sanitizer build): GoldenCheck passes on the 366 vectors and gives back the live
risk table; one vector of each kind changed beyond its tolerance (clock, NYSE, AddTradingDays, BusinessDays, ORX exit,
F1 score, F1 feature, riskbp, risk-table rate and text, a D2 rate, a D2 text above the 10 % cap, Wilder value and NaN,
SMA value and NaN) is refused with a message naming it; a change of 1e-14 relative passes; 0.12 ms per call.
29 checks, 0 failed.

`test_release.py`:

| Check | Result |
|---|---|
| dist = amalgam(src) now, byte for byte; CR_BUILD = sha256 of the text; debug = release + `CR_DEBUG` | yes |
| Harness constants in the dist file (`CR_HARNESS`, `CR_NO_GUARD`, `CR_DEBUG`, `CR_IDX_TRACE`, any `MOCK_`) | none; `CR_XAU_COMM_PTS` defined once, under `#ifndef`, as 6; `CR_BRK_NOTIONAL_X` once, under `#ifndef`, as 20.0 (new) |
| The 15 inputs of SPEC 1, in order, types and defaults (new: `InpGuard`; D2's defaults) | exact; `InpScript` and `InpScriptDir` only inside `#ifdef CR_HARNESS` |
| MQL5 subset (fmax/fmin, `->`, `new`, `#import`, `virtual`, `template`, function macros, `Sleep`) | none |
| Builds: harness, sanitizer, release, debug release, release + `CR_NO_GUARD`, release + `CR_XAU_COMM_PTS=0`, release + `CR_BRK_NOTIONAL_X=1000` (new) | 0 warnings each (the `settled` warning of the `CR_NO_GUARD` build is gone) |
| Release build, one week of 2021 in the mock, InpTrade true, the default inputs | `SELFTEST ok=1 golden=366`, `INIT harness=0 comm_pts=6 risk=0:10;3000:5;10000:2;20000:1`, the same risk on the PLAN line, 34 orders sent |
| The journal of that run (new, F9) | 2,883 lines in the file, 2,420 of them `rp=1`; 463 lines Printed, none `rp=1`; 207 file flushes for 7,200 timer passes |
| Release + `CR_NO_GUARD` | `SELFTEST ok=0 why=CR_NO_GUARD is set in a build without CR_HARNESS`, 0 orders, intents skipped as `selftest` |
| Release + `CR_XAU_COMM_PTS=0` | `SELFTEST ok=0 why=CR_XAU_COMM_PTS is not 6`, 0 orders |
| Release + `CR_BRK_NOTIONAL_X=1000` (new) | `SELFTEST ok=0 why=CR_BRK_NOTIONAL_X is not 20`, 0 orders |
| Harness build of a copy of the dist file with one golden F1 score changed | `SELFTEST ok=0 why=golden f1_score 0: ...`, 0 orders |
| Debug file | 313,605 BAR lines (the bar dump), SELFTEST ok |

### Speed and the sanitizer

| What (SPEC 7, 8) | Result | Limit |
|---|---|---|
| Full in-sample ten-sleeve replay, 2013-2021, 8.78 million bars, `InpTrade` false | 16.5 s (switches off), 17.2 s (on) | under 3 min |
| A start's rebuild: 172,682 minutes (120 days of gold, 60 of the others) | 0.26 s of mock replay (1.2 s for the whole process) | under 5 s |
| The same full replays under the sanitizer build | 299 s and 287 s, journals byte-identical | |
| The 2021 clean world under the sanitizer (trading, J's follower and broker) | 412 s, journal and deals identical | |
| GoldenCheck at OnInit (sanitizer build) | 0.12 ms | |

With trading on, the nine-year replay takes about 9 minutes in the mock (T6's continuous runs: 568 s and
557 s, the two settings side by side), because the EA reads the whole deal history at least once a minute (SPEC R5)
and the mock scans every deal per call (section 6).

## 4. Every remaining difference, with its cause

On the same bars, the shipped file and the lab code differ only here (the January 2013 GFP stops of step K's list are
gone: the rebuilt frame no longer holds the 20 gold bars of 2012-12-31 that the EA masks, X1):

| # | Where | Count | Cause | Status |
|---|---|---|---|---|
| 1 | NQB stops and stop exits | 1 trade in sample, 1.6e-16 relative (T4); in the 2021 worlds 3 stops and 1 exit, at most 1.9e-16 (T8); after restarts a few trades per setting, at most 2.2e-16 (T6) | numpy's log against the C library's log (one unit in the last place on 6,538 of 1,469,276 US100 returns); after a restart the rolling sums start from a different first minute, so their rounding differs in the last bits | inside SPEC 7's 1e-12 |
| 2 | GFP hole day 2013-05-31 | 1 trade only in the EA | the gold data stops at 16:39 New York; the lab's 16:45 test reads that future hole | classified (SPEC 7) |
| 3 | D4H, ORX | 1 lab trade each open at the frame end | its exit falls in 2022 | left out (SPEC 7) |
| 4 | EA orders without a lab order | BKB 29, BKE 19, F1B 3, F1E 3, NQB 5 | no kept bar within the 5-minute window: the lab drops them by looking ahead, the paper lets them expire; they never trade | no trade difference |

Execution and account differences (the paper is unchanged in each case):

| # | Where | Count | Cause | Status |
|---|---|---|---|---|
| 5 | Late gold intents sized on the larger of paper and quote risk (P1) | 2018-2021, F3S: quote risk larger on ORX 163, GFP 95, D4H 87; lots smaller on ORX 114, GFP 41, D4H 60 (D2: 142, 65, 75) | SPEC 4.2: a stop, limit or OCO fill is sent one bar late at the quote | SPEC 9.1; far more than SPEC 4.2's estimate for 2013-2021 (16 donch, 20 orb, 0 GFP): for the lead |
| 6 | D4H 2021-08-08 (gold flash crash) | 1 trade: the real exit is 0.12 USD per oz better than the paper's (5.56 USD on 0.47 lots) | the paper's new trail stop was already past the next open: the follower closes at the open (SPEC 4.4), the paper books its stop there with stop slippage | SPEC 9.4 |
| 7 | Tick mode stop exits | 2021: 423 of 1,348 real exits fill at the triggering tick, not at the stop price | the mock's four ticks a minute (open, low, high, close) | mock model |
| 8 | ETH sleeves NOT_READY until 2018-03-02 | BKE 8, F1E 9 intents in February 2018 | ETH's data starts 2018-01-01; SPEC 2.2 needs 60 days | SPEC 2.2 |
| 9 | Restarts (T6) | see T6: entries delayed by a start or an outage, exits in a start; then lots only, and a few cap skips | start-up windows and outages delay or miss real entries and exits; the shared account's balance then differs, so later lots differ and a cap can bind differently; no close the EA decides against an open paper trade any more (F1) | SPEC 4.8, 9.9, 9.16 |
| 10 | Volume cap | 2018-2021: F3S 52 BKE and 90 F1E orders above 100 lots; D2 1,500 requests (N30 337, OC4 242, BKB 17, BKE 386, F1B 34, F1E 411, NQB 66, ORX 7) | CR_Broker cuts at SYMBOL_VOLUME_MAX (`SEND cut=vmax`); the lab has no cap; D2's balance reaches millions of EUR in sample | FP's real caps: Mac item 10.6 |
| 11 | The 20 x balance cap (new to list) | D2 2018-2021: 10 requests (N30 4, OC4 2, ORX 4); none under F3S, F2S, F1S | CR_Broker cuts a position's value to 20 x the balance; the lab has no such cap; a 10 % stake with a tight stop meets it at the start | kept (SPEC 1, 4.3); T7b raises it in its harness only |
| 12 | Crypto margin at 1:2 (a reading) | D2 462, S7 250 MARGIN skips (T7b reading) | if FP's crypto margin is 50 %, open crypto positions tie up the balance | FP's real margin: Mac item 10.6 |

Against the official trades (the lab's own frames, not the robot), the 2-digit export moves razor decisions: N30 1, OC4
1, BKE 1, F1E 2 (+1 added), NQB 1, D4H 8 of 495; prices otherwise within 0.014 USD (Mac items 10.3 and 10.6).

## 5. Requests and decisions for other owners

| # | Owner | File | Request | Status |
|---|---|---|---|---|
| 1 | J | `src/CR_Guards.mqh` | the unused `settled` variable of `CR_NO_GUARD` builds | done in this round (K1) |
| 2 | I and J, then K | `src/CR_Ledger.mqh`, `src/CR_Broker.mqh`, `src/CR_Types.mqh` | Move `CR_MAGIC_ROBOT_LO/HI` (20261201, 20261289) to CR_Types.mqh and drop the copies (`CR_BRK_MAGIC_LO/HI` in CR_Broker). | open (cosmetic) |
| 3 | C | `src/CR_Paper.mqh` | Add count/at accessors for the pending queue, the rule exits and the trade order (CR_Follower reads `g_pap_q`, `g_pap_qn`, `g_pap_x`, `g_pap_xn`, `g_pap_t` directly, read only). | open (cosmetic) |
| 4 | I | `src/CR_Sizing.mqh` | Optional: use `RegStakeFactor` once it moves to CR_Types (SizFactor is a copy). | open (optional) |
| 5 | Lead | `check/export_frames.py` | the 20 gold bars of 2012-12-31 17:00-17:58 New York | done (X1): dropped from the bars and the rebuilt frame; T2 and test_GFP fail if they come back |
| 6 | Lead | `SPEC.md` | the wording the steps asked for (below) | the §4.1 bid-flat clause is gone (v2.1); the others stay open, none changes behaviour |
| 7 | Lead, then I, J, K | `SPEC.md`, `src/`, tests | PROTOCOL_V3 Addendum G: D2 as the robot's plan, the guard off | done (F3): D2 is the default, S7 and F3S are presets; when the user picks another X, only the four plan inputs change (`0:X;3000:X/2;10000:X/5;20000:X/10`, no stop, guard off) |

SPEC wording still asked by the steps (for the lead; none changes behaviour):
- §3 N30 and OC4 (D), F1 (E) and NQB (F): their orders carry `void_le` (the lab's own "exit after entry" filter); §7's
  HOLE_RULE then needs no exception for them.
- §3 NQB (F): "running sums as pandas makes them", not "re-summed daily"; the [g+1, g+2] window is one order for g+1, sent
  again for g+2 only when g+1 has no BTC bar.
- §3 GFP (G): the ATR is "the last UTC hour with bars that ended by 13:30"; in sample the lab's skip set is the 26
  calendar Fridays plus one hole day (2013-05-31).
- §4.8 D4H row (H): "the latest 4h boundary at or before o" is not always an upper bound (a Friday 23:59 server decision);
  since v2.1 a NOT_READY close waits for the first READY check and 10 min, so the reconcile normally decides first.
- §5 (I): "a withdrawal moves neither B/ref nor the risk rung" holds only while B <= P_in.
- §7 (E, H): "rounding changed no trade" is not true on the 2-digit export: BKE 1, F1E 2, D4H 8 trades of the official
  frames differ on the rebuilt ones (EA and lab agree on the same bars).
- §2.1 (A): the last gold bar on short holidays starts between 11:59 and 14:16 New York.
- §4.2 / §9.1 (K, from T7b): late intents sized on the quote risk are far more than the SPEC's estimate (see T7b).

## 6. What only the user's Mac (or the lab) can check (SPEC 10)

Until each item is settled, its default holds; items 1 and 2 block trading until done.

| # | Item | What to look at | Default meanwhile |
|---|---|---|---|
| 10.1 | MetaEditor compile and the self-test on the real compiler | `dist/ClaudeRobot.mq5` compiles with 0 errors and 0 warnings; the first journal lines show `SELFTEST ok=1 why= golden=366` and `INIT ... risk=0:10;3000:5;10000:2;20000:1 ... k1t=` with the plan and the K1 table as typed. The file keeps SPEC 1's subset (checked by test_release.py and to_cpp.py), but MetaEditor's own warnings cannot be proven here (the review's F12: `-Wshadow` 0, `-Wconversion` 4 long-to-double; a member named `group`). Golden doubles allow 1e-12 relative; times and dates are exact. | no trading |
| 10.2 | Strategy Tester run of the debug file on FP 2021 | real ticks (else 1-minute OHLC), `InpTrade` false, the three switches and the four plan inputs set explicitly; replay the dumped BAR lines in the harness in tester mode (R12): the journal must match line for line. The tester copy is an observer; its intents are sized NOTRADE at activation like the VPS copy's (F6). | no trading |
| 10.3 | What `MqlRates.spread` holds | the bar's minimum spread or the closing one, against the ReleveFP files. The export rounds the bid to 2 digits; on the official frames this moves N30 1, OC4 1, BKE 1, F1E 2, NQB 1 and D4H 8 trades (section 3, T4). | ask = bid + spread |
| 10.4 | Server = New York + 7 h across a summer-time switch | the CLOCK line stays quiet in March and November. | the rule; CLOCK (SPEC 6.5) |
| 10.5 | FP sessions, crypto weekends, Friday close, holiday hours | the lab writes `InpExtraClosures` for the next 12 months (at most about 6 windows or 14 dates fit in MetaTrader's 255 characters). FP's Friday gold session must run to 16:46 New York (23:46 server), else GFP skips the Friday and pushes it (F7). Weekend crypto quotes trade nothing (F2). | built-in closures, shortened by the broker's sessions |
| 10.6 | Symbol specifications | digits, contract sizes, the US100 minimum lot, EUR tick values, stops and freeze levels, filling, hedging; **margin**: at a crypto margin of 50 % (1:2) the margin check skips 462 D2 requests of 2018-2021 (250 under S7) (T7b reading); **SYMBOL_VOLUME_MAX**: D2's growth to millions of EUR takes lots above 100 on 1,500 requests of 2018-2021 (N30 337, OC4 242, BKB 17, BKE 386, F1B 34, F1E 411, NQB 66, ORX 7; CR_Broker cuts them, `SEND cut=vmax`). | read live; the harness uses fp_costs.json and 0.89 |
| 10.7 | Deposits and withdrawals as `DEAL_TYPE_BALANCE`; a closing deal carries the closing request's magic | the guard's mark (magic 20261290; only with `InpGuard` true); the minimum-lot mark trade covers the other case. | the history; B(T) from the balance |
| 10.8 | Stop deals' magic and reason; comments kept | `LatestExit` reads `POSITION_TIME`, the comment only cross-checks. | position id, magic and time |
| 10.9 | VPS history depth, `SERIES_SYNCHRONIZED`, replay time, Max bars 500,000, `TERMINAL_VPS` | the four READY lines; the REBUILD line's `ms` (in the mock a start rebuilds 120 days of gold and 60 of the others in about 0.26 s of mock replay). | NOT_READY until deep and complete; NOT_READY exits wait 10 min |
| 10.10 | Tick timing, open slippage, LATEBAR rate | journal SEND/FILL against the paper; LATEBAR lines. | 2 s grace, one rebuild per revision |
| 10.11 | FP's gold commission | `COST` lines: `DEAL_COMMISSION` of the first gold fills against 0.06 USD per oz. | 6 points; a gap over 1 point is pushed |
| 10.12 | Two shadow weeks | SPEC 10.12, step by step: VPS copy and Mac copy both with `InpTrade` false (by the migration procedure); compare their live lines, which must be equal (F6), then a harness replay of the same bars; then `InpTrade` true. | none |
| 10.13 | Before real money | the plan is the user's: default D2 (no plan stop, guard off); the user is told again that a fall of half or more comes in 73.2 % / 88.3 % of D2's validation-year paths (paper / half edge) and that the account can be lost, and confirms D2 or a preset (S7, F3S) of SPEC 1; `InpPlanStart` is set; the three switches stay off on the real account until their demo period is judged. | no real-money trading |
| 10.14 | K1 thresholds | the lab gives T(2026) with 17 digits as `2026:T` in `InpK1T`, then each 1 January. | K1 off |
| 10.15 | Migration (new, F10) | SPEC 10.15 step by step: the Mac's Algo Trading off; inputs set with `InpTrade` true (a Saturday is best); migrate; check the VPS's INIT line (`vps=1 observer=0 entries_off=0`); `InpTrade` false on the Mac. Never Algo Trading on with `InpTrade` true on the Mac's demo chart. | a migration by any other order can let two copies trade, or turn the VPS copy's entries off |

Found during the build, also for the Mac:
- **MathLog.** NQB's sigma uses log returns. numpy's log and the C library's differ by one unit in the last place on
  6,538 of 1,469,276 US100 returns; MetaTrader's MathLog is a third implementation. The effect stays near 1e-16 (inside
  SPEC 7's 1e-12), but a decision exactly at the 6-sigma threshold could flip (none lies within 1e-9 in sample).
- **History reads.** The EA reads the whole deal and order history (`HistorySelect(0, now + 1 day)`, SPEC R5) at least
  once a minute. In the mock, which scans every deal per call, nine years of trading take about 9 minutes of replay
  against about 17 s without trading. The terminal's own cost with years of history is unknown: watch the timer's load on
  the VPS.
