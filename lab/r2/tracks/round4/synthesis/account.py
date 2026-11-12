"""PROTOCOL_V3 Addendum J, round 4 lead synthesis, step 2: the ten's weekly Sharpe in sample, with and without the
kept rules, at equal weekly swing. IN SAMPLE ONLY (common.read_is: entry_time AND exit_time < 2022-01-01 in the read).

No round-4 rule passed in sample (verification.json), so the kept set is empty and "with" equals "without".
The ten are measured as the lab's syntheses do: plain sum of the official one-position chains, 1 R per trade, weekly
sums of R booked at the exit, every calendar week of 2014-2021 counted (empty weeks = 0), Sharpe x sqrt(52); FP costs
as in the official trade files. Both week conventions are given (server weeks NY+7h, and UTC W-SUN weeks), and the
engineers' variant (trades ENTERED 2014-2021 only) for comparison with their 2.537.

INFORMATION ONLY, deciding nothing: the in-sample main of IDXRS_1000 (failed the t bar, not kept) added at 1 R per pair,
the account then scaled back to the ten's weekly swing; and the judge's break-even (a newcomer of weekly Sharpe s and
correlation c adds only if s > c x S_account) with the best-weighting bound S^2 + (s - cS)^2 / (1 - c^2).
Output: lab/r2/tracks/round4/synthesis/account.json
"""
import json
import os

import numpy as np
import pandas as pd

from common import HERE, R4, TEN, read_is, official, weekly, sharpe, corr, dump

ver = json.load(open(os.path.join(HERE, "verification.json")))
kept = [k for k, v in ver.items() if not k.startswith("_") and v["passes"]]
assert kept == [], kept  # nothing passed in sample, so nothing can be kept

ten = {f"{n}__{s}": official(n, s) for n, s in TEN}


def measures(w):
    w = np.asarray(w, float)
    return {"weeks": int(len(w)), "sharpe": round(sharpe(w), 4), "mean_week_R": round(float(w.mean()), 4),
            "sd_week_R": round(float(np.std(w, ddof=1)), 4), "total_R": round(float(w.sum()), 2),
            "losing_weeks_pct": round(float(100 * (w < 0).mean()), 2), "worst_week_R": round(float(w.min()), 2)}


out = {"kept_rules": kept, "convention": __doc__.split("Output:")[0].strip()}
for conv in ("server", "wsun"):
    w10 = np.sum([weekly(t, conv) for t in ten.values()], axis=0)
    out[f"ten_{conv}"] = measures(w10)
# trades booked in the window: server weeks run Monday 00:00 server (= Sunday 17:00 New York) to the next Monday
lo = pd.Timestamp("2013-12-30", tz="America/New_York") - pd.Timedelta(hours=7)
hi = pd.Timestamp("2022-01-03", tz="America/New_York") - pd.Timedelta(hours=7)
out["ten_server"]["trades_booked"] = int(sum(((t.exit_time >= lo) & (t.exit_time < hi)).sum() for t in ten.values()))
lo_u, hi_u = pd.Timestamp("2013-12-30", tz="UTC"), pd.Timestamp("2022-01-03", tz="UTC")
out["ten_wsun"]["trades_booked"] = int(sum(((t.exit_time >= lo_u) & (t.exit_time < hi_u)).sum() for t in ten.values()))
# the engineers' variant: trades entered 2014-01-01..2021-12-31 only, W-SUN UTC weeks
start = pd.Timestamp("2014-01-01", tz="UTC")
ten_e = {k: t[t.entry_time >= start] for k, t in ten.items()}
w10e = np.sum([weekly(t, "wsun") for t in ten_e.values()], axis=0)
out["ten_wsun_entries_2014_2021"] = {**measures(w10e), "trades": int(sum(len(t) for t in ten_e.values()))}
out["with_kept_rules"] = "identical to the ten alone: no rule kept"

# ------------------------------------------------------------------------------------------- information only
idx = read_is(os.path.join(R4, "idxrs_1000", "trades_01_main.parquet"), columns=["entry_time", "exit_time", "R"])
info = {}
for conv in ("server", "wsun"):
    w10 = np.sum([weekly(t, conv) for t in ten.values()], axis=0)
    wi = weekly(idx, conv)
    S, s, c = sharpe(w10), sharpe(wi), corr(wi, w10)
    w_with = w10 + wi
    k = float(np.std(w10, ddof=1) / np.std(w_with, ddof=1))
    best = float(np.sqrt(S ** 2 + max(s - c * S, 0.0) ** 2 / (1 - c ** 2)))
    info[conv] = {"idxrs_weekly_sharpe": round(s, 4), "corr_with_ten": round(c, 4), "break_even_s=c*S": round(c * S, 4),
                  "ten": round(S, 4), "ten_plus_idxrs_1R": round(sharpe(w_with), 4),
                  "ratio_1R": round(sharpe(w_with) / S, 4),
                  "scale_to_equal_swing": round(k, 4),
                  "mean_week_R_equal_swing": {"ten": round(float(w10.mean()), 4),
                                              "ten_plus_idxrs": round(float(w_with.mean() * k), 4)},
                  "best_weighting_bound": round(best, 4), "best_ratio": round(best / S, 4)}
out["information_only_idxrs_1000_not_kept"] = info
dump(out, os.path.join(HERE, "account.json"))
print(json.dumps({k: v for k, v in out.items() if k != "convention"}, indent=1))
