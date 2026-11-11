"""Construction (a): exit shaping pushed to the extreme on the ten validated rules. IN SAMPLE ONLY.

Entries are the frozen rules' own orders. Only the exits change:
    target  k x R0 from the fill           (k = 0.2, 0.3, 0.5; R0 = the rule's own initial risk)
    stop    m x R0 from the fill           (m = 1: the rule's own stop and trailing stop, untouched;
                                            m = 2, 3: a plain stop at m x R0, the rule's trailing stop is dropped)
    evening exit ("eve")                   the trade is closed at 23:50 FP server time (16:50 New York) of the server
                                            day of its FILL if it is still open (never later than the rule's own time
                                            exit). The fill bar of every order is read from a first every-signal pass
                                            (the fill of an order does not depend on any exit), so the rule is causal.
The position size is the SAME as in the validated rule (results are in units of the base stake = pnl / R0), so a
stop at 3 x R0 really risks 3 base stakes on one trade.

Zero-edge control (the "shape alone"): the same exits on market entries taken one minute after the same fill
minutes with a COIN-FLIP direction, mid prices (no cost), N_DRAWS draws -> what the shape gives when the entry
carries no information at all.

    python3 a_shape.py            -> results/r2/jours/a_shape.json, a_shape_trades/<variant>__<kind>.parquet
"""
import importlib.util
import json
import os
import sys
import time
import zlib

import numpy as np
import pandas as pd

import common as C
import goldlab as gl
from goldlab import r2
from goldlab.sim import apply_spread_mult, simulate

sys.path.insert(0, os.path.join(C.LAB, "r2", "tracks", "shape"))
N_DRAWS = 20
VARIANTS = [("base", None, 1, False), ("eve_only", None, 1, True)]
for _k in (0.5, 0.3, 0.2):
    for _m in (1, 2, 3):
        for _e in (False, True):
            VARIANTS.append((f"T{_k}_S{_m}{'_eve' if _e else ''}", _k, _m, _e))


def _recalc():
    spec = importlib.util.spec_from_file_location("r2_recalc", os.path.join(C.LAB, "r2", "recalc.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["r2_recalc"] = m
    spec.loader.exec_module(m)
    return m


def initial_risk(m1, o):
    """Copy of r2/tracks/shape/strategy.py::initial_risk (R0 known at the entry minute)."""
    n = len(o)
    side = o["side"].to_numpy(np.int64)
    et = o["etype"].to_numpy(np.int64) if "etype" in o else np.zeros(n, np.int64)
    ei = np.clip(o["entry_i"].to_numpy(np.int64), 0, len(m1) - 1)
    lv = o["level"].to_numpy(float) if "level" in o else np.full(n, np.nan)
    ao, bo = m1["ao"].to_numpy(float), m1["bo"].to_numpy(float)
    fill = np.where(et > 0, lv, np.where(side > 0, ao[ei], bo[ei]))
    st = o["stop"].to_numpy(float) if "stop" in o else np.full(n, np.nan)
    sd = o["stop_dist"].to_numpy(float) if "stop_dist" in o else np.full(n, np.nan)
    return np.where(np.isnan(st), sd, np.abs(fill - st))


def evening_index(m1, fill_times):
    """M1 index of the 23:50 server-time bar (16:50 New York) of the server day of each fill."""
    sd = C.server_time(fill_times).normalize()
    eve = (sd + pd.Timedelta(hours=16, minutes=50)).tz_localize("America/New_York", ambiguous=True, nonexistent="shift_forward")
    return gl.exit_index(m1, pd.DatetimeIndex(eve.tz_convert("UTC")))


def variant_orders(o, r0, eve_i, k, m, eve):
    v = o.copy()
    v["r0"] = r0
    if k is not None:
        v["target"] = np.nan
        v["target_dist"] = k * r0
    if m > 1:
        v["stop"] = np.nan
        v["stop_dist"] = m * r0
        v["trail"] = np.nan
        v["be"] = np.nan
    if eve:
        x = v["exit_i"].to_numpy(np.int64).copy()
        ok = eve_i >= 0
        x[ok] = np.where(x[ok] >= 0, np.minimum(x[ok], eve_i[ok]), eve_i[ok])
        v["exit_i"] = x
    return v


def keep_is(t):
    t = t[t.entry_time < C.IS_END]
    return pd.DataFrame({"t_in": t.entry_time.to_numpy(), "t_out": t.exit_time.to_numpy(), "side": t.side.to_numpy(),
                         "entry": t.entry.to_numpy(float), "r0": t.r0.to_numpy(float), "pnl": t.pnl.to_numpy(float),
                         "res": (t.pnl / t.r0).to_numpy(float), "reason": t.reason.to_numpy()})


if __name__ == "__main__":
    recalc = _recalc()
    sl = [s for s in recalc.sleeves() if (s[1], s[2]) in C.SLEEVES]
    sl.sort(key=lambda s: s[2])
    os.makedirs(os.path.join(C.OUT, "a_shape_trades"), exist_ok=True)
    acc = {(v[0], kind): [] for v in VARIANTS for kind in ("gross", "net")}
    ctl = {(v[0], d): [] for v in VARIANTS for d in range(N_DRAWS)}
    last = None
    for track, name, sym, mo, params in sl:
        t0 = time.time()
        if sym != last:
            m1 = C.load_is(sym)
            mk = apply_spread_mult(m1, 0.0)
            last = sym
        key = f"{name}_{sym}"
        for kind, frame, costs in (("net", m1, r2.costs(sym)), ("gross", mk, r2.GROSS)):
            o = mo(frame, **params).reset_index(drop=True)
            for c in ("trail", "be", "stop", "stop_dist", "target", "target_dist"):
                if c not in o:
                    o[c] = np.nan
            if "etype" not in o:
                o["etype"] = 0
            r0 = initial_risk(frame, o)
            o["r0"] = r0
            ev = simulate(frame, o, sym=sym, costs=costs, no_overlap=False)      # pass 1: fill bar of every order
            eve_i = np.full(len(o), -1, np.int64)
            eve_i[ev.index.to_numpy()] = evening_index(frame, ev.entry_time)
            fill_i = np.full(len(o), -1, np.int64)
            fill_i[ev.index.to_numpy()] = frame.index.get_indexer(ev.entry_time)
            for vname, k, m, eve in VARIANTS:
                t = simulate(frame, variant_orders(o, r0, eve_i, k, m, eve), sym=sym, costs=costs, no_overlap=True)
                t = keep_is(t)
                t.insert(0, "sleeve", key)
                acc[(vname, kind)].append(t)
            if kind == "gross":                                                    # zero-edge control, coin-flip side
                ok = fill_i >= 0
                rng = np.random.default_rng(zlib.crc32(key.encode()))
                base = pd.DataFrame({"entry_i": fill_i[ok] + 1, "etype": 0, "r0": r0[ok],
                                     "exit_i": o["exit_i"].to_numpy(np.int64)[ok]})
                ev_ok = eve_i[ok]
                for d in range(N_DRAWS):
                    side = rng.choice(np.array([-1, 1]), size=int(ok.sum()))
                    for vname, k, m, eve in VARIANTS:
                        c = base.copy()
                        c["side"] = side
                        c["stop_dist"] = max(m, 1) * c.r0
                        if k is not None:
                            c["target_dist"] = k * c.r0
                        if eve:
                            c["exit_i"] = np.where(c.exit_i >= 0, np.minimum(c.exit_i, ev_ok), ev_ok)
                        c = c[c.exit_i > c.entry_i]
                        t = keep_is(simulate(frame, c, sym=sym, costs=r2.GROSS, no_overlap=True))
                        ctl[(vname, d)].append(t[["t_in", "t_out", "res"]])
        print(key, "%.0fs" % (time.time() - t0), flush=True)
    out = {}
    for vname, k, m, eve in VARIANTS:
        rec = {"k": k, "m": m, "eve": eve}
        for kind in ("gross", "net"):
            t = pd.concat(acc[(vname, kind)], ignore_index=True)
            t.to_parquet(os.path.join(C.OUT, "a_shape_trades", f"{vname}__{kind}.parquet"))
            for per, tt in (("common", t[t.t_in >= C.COMMON_START]), ("whole", t)):
                s = C.stats(C.daily(tt.t_out, tt.res))
                s["trades"] = int(len(tt))
                s["trade_win_pct"] = round(float((tt.res > 0).mean() * 100), 1)
                s["halves"] = C.halves(C.daily(tt.t_out, tt.res))
                rec[f"{kind}_{per}"] = s
        z = []
        for d in range(N_DRAWS):
            t = pd.concat(ctl[(vname, d)], ignore_index=True)
            t = t[t.t_in >= C.COMMON_START]
            day = C.daily(t.t_out, t.res)
            s = C.stats(day)
            s["p_half"] = C.week_bootstrap(day, n=200, seed=d)
            z.append(s)
        z = pd.DataFrame(z)
        rec["zero_edge_common"] = {c: round(float(z[c].mean()), 2) for c in
                                   ("green_days", "green_weeks", "green_months", "avg_green", "avg_red", "total",
                                    "worst_day", "worst_week", "max_dd", "p_half")}
        rec["zero_edge_common"]["worst_week_min_over_draws"] = round(float(z.worst_week.min()), 2)
        rec["zero_edge_common"]["worst_day_min_over_draws"] = round(float(z.worst_day.min()), 2)
        rec["zero_edge_common"]["total_sd_over_draws"] = round(float(z.total.std()), 1)
        out[vname] = rec
        C.log_trial({"construction": "a_shape", "variant": vname, **rec}, "a_shape_trials.jsonl")
    json.dump(out, open(os.path.join(C.OUT, "a_shape.json"), "w"), indent=1)
    rows = []
    for v, rec in out.items():
        for kind in ("gross", "net"):
            s = rec[f"{kind}_common"]
            rows.append(dict(variant=v, kind=kind, **{c: s[c] for c in ("trades", "trade_win_pct", "green_days", "green_weeks",
                        "green_months", "avg_green", "avg_red", "red_in_greens", "total", "worst_day", "worst_week", "max_dd")}))
        z = rec["zero_edge_common"]
        rows.append(dict(variant=v, kind="zero", green_days=z["green_days"], green_weeks=z["green_weeks"],
                         green_months=z["green_months"], avg_green=z["avg_green"], avg_red=z["avg_red"],
                         total=z["total"], worst_day=z["worst_day"], worst_week=z["worst_week"], max_dd=z["max_dd"]))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.OUT, "a_shape_common.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print(df.to_string())
