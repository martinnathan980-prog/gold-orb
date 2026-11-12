"""Self-check of the ocm4 candidate by a separate code path (no make_orders, no engine for the cut):
start from the official ocm4 trades (entry_time < 2022-01-01, read with the filter), find for each trade the 15:55
New York exit bar of its day, the mid-life checkpoint, the decision bar and the state by hand from the in-sample
frame; where u < 0.5 R replace the exit by the next bar's open (bid x (1 - 0.2 bp) long, ask x (1 + 0.2 bp) short;
intraday, so no swap).  Compares the 2018-2021 totals with s2_rules.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def main():
    t = C.official("ocm4", "us100")
    m1 = C.load_is("us100")
    idx = m1.index
    ny = t.entry_time.dt.tz_convert(C.NY)
    t1555 = (ny.dt.normalize() + pd.Timedelta(hours=15, minutes=55)).dt.tz_convert("UTC")
    xi = C.gl.exit_index(m1, pd.DatetimeIndex(t1555))
    t_end = idx[np.clip(xi, 0, len(idx) - 1)]
    t_fill = pd.DatetimeIndex(t.entry_time)
    t_check = t_fill + (t_end - t_fill) / 2
    d = np.searchsorted(idx.values, t_check.values, side="left") - 1          # last bar starting before t_check
    d_close = idx[d] + pd.Timedelta(minutes=1)
    # still open at the close of bar d: a stop exit is stamped bar start + 1 min, a time exit at the bar start
    exit_bar_start = t.exit_time - pd.to_timedelta(np.where(t.reason == "time", 0, 1), unit="m")
    still_open = exit_bar_start.values > idx[d].values
    s = t.side.to_numpy()
    q = np.where(s > 0, m1["bc"].to_numpy()[d], m1["ac"].to_numpy()[d])
    risk = (t.entry - t.stop).abs().to_numpy()
    u = s * (q - t.entry.to_numpy()) / risk
    fire = still_open & (u < 0.5)
    slip = C.r2.costs("us100").slip_mkt_bps * 1e-4
    px = np.where(s > 0, m1["bo"].to_numpy()[d + 1] * (1 - slip), m1["ao"].to_numpy()[d + 1] * (1 + slip))
    R_cut = s * (px - t.entry.to_numpy()) / risk                                # no overnight: swap 0
    R_new = np.where(fire, R_cut, t.R.to_numpy())
    w = (t.entry_time >= C.COMMON_START).to_numpy()
    pre = ~w
    tr = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(C.RES, "trials.jsonl"))}
    v = tr["ocm4:us100|NP|t=50%|y=0.5"]["fp"]
    out = {"window_2018_2021": {"n": int(w.sum()), "fired": int((fire & w).sum()), "total_base": round(float(t.R[w].sum()), 4),
                                "total_new_selfcheck": round(float(R_new[w].sum()), 4),
                                "total_new_s2": v["common"]["total_R"], "n_fired_s2": v["common"]["n_fired"]},
           "pre_2018": {"n": int(pre.sum()), "fired": int((fire & pre).sum()), "total_base": round(float(t.R[pre].sum()), 4),
                        "total_new_selfcheck": round(float(R_new[pre].sum()), 4), "total_new_s2": v["pre"]["total_R"]},
           "checkpoint_clock_ny": pd.Series(pd.DatetimeIndex(d_close).tz_convert(C.NY).strftime("%H:%M")).value_counts().head(5).to_dict()}
    C.jdump(out, os.path.join(C.RES, "selfcheck_ocm4.json"))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
