"""Research helpers for track `ml` (round 2). In-sample only: candidate tables are built on frames cut
at 2022-01-01, and r2.evaluate() only ever returns in-sample reports."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

import strategy as S  # noqa: E402

TRACK = "ml"
RES = "/home/user/gold-orb/lab/results/r2/ml"
IS_END = "2022-01-01"
os.makedirs(RES, exist_ok=True)
os.makedirs(S.MODEL_DIR, exist_ok=True)


def n_trials():
    p = os.path.join(RES, "trials.jsonl")
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


def trial(sym, params, stage, full=False, note=""):
    """Evaluate one configuration in-sample through the official toolkit and log it (always)."""
    ev = r2.evaluate(sym, S.make_orders, params, full=full)
    r2.log_trial(TRACK, sym, params, ev)
    row = {"k": n_trials(), "stage": stage, "note": note, "sym": sym, "params": params, "full": full,
           "is": ev["is"], "is_bps_per_trade": ev.get("is_bps_per_trade")}
    for k in ("is_stress", "is_gross", "is_every_signal"):
        if k in ev:
            row[k] = ev[k]
    if "is_gross_bps_per_trade" in ev:
        row["is_gross_bps_per_trade"] = ev["is_gross_bps_per_trade"]
    with open(os.path.join(RES, "trials_detail.jsonl"), "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return ev


def line(ev, extra=""):
    r = ev["is"]
    if r.get("n", 0) == 0:
        return "n=0"
    return (f"n={r['n']:5d} /yr={r['trades_per_year']:6.1f} win={r['win_rate']:.3f} PF={r['pf']:.3f} "
            f"expR={r['expectancy_R']:+.4f} t={r['t_stat']:+.2f} yrs={r['years_pos']} "
            f"L={r['long_R']:+.1f}({r['long_n']}) S={r['short_R']:+.1f}({r['short_n']}) "
            f"hold={r['avg_hold_h']}h bps={ev.get('is_bps_per_trade')} {extra}")


def is_frame(sym):
    return r2.load(sym, end=IS_END)


def table(sym, gen_params, tag, force=False, gross=True):
    """Candidate table of one market for one generator setting (in-sample frame only): features plus
    the outcome of EVERY candidate taken on its own (engine, FP costs, overlaps allowed) = the label.
    Rg = same without any cost (mid prices)."""
    path = os.path.join(RES, f"cand_{sym}_{tag}.parquet")
    if os.path.exists(path) and not force:
        return pd.read_parquet(path)
    m1 = is_frame(sym)
    f = S.candidates(m1, **gen_params).copy()
    f["cid"] = pd.DatetimeIndex(f["t_dec"]).asi8
    t = r2.run(sym, S.make_orders, gen_params, "fp", no_overlap=False, m1=m1)
    f = f.merge(t[["cid", "R", "reason", "hold_min", "entry", "risk", "pnl"]], on="cid", how="left")
    if gross:
        tg = r2.run(sym, S.make_orders, gen_params, "gross", no_overlap=False, m1=m1)
        f = f.merge(tg[["cid", "R"]].rename(columns={"R": "Rg"}), on="cid", how="left")
    else:
        f["Rg"] = np.nan
    f["sym"] = sym
    f["year"] = pd.DatetimeIndex(f["t_dec"]).year
    f.to_parquet(path)
    return f
