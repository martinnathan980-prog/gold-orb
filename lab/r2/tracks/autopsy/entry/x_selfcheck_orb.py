"""Addendum H, lens `entry` -- self-check of the orb_asia_2d_buf10 retest cells by a plain bar-by-bar loop written
from the specification (no goldlab.sim, no chain() of this lens): RT30_mkt and RT30_skip with the stop at the rule's
price, FP costs, in sample.  Not a new variant: it recomputes declared cells by another code path and compares the
trade lists with the engine's (results/r2/autopsy/entry/cells/orb_asia_2d_buf10__xauusd.parquet).
Writes results/r2/autopsy/entry/selfcheck_orb.json."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import COMMON_START, MIN_NS, RES, arrays, build_orders, costs, jdump, load_is, np, pd  # noqa: E402
from goldlab.data import trading_day  # noqa: E402


def run(m1, A, o, c, N, fallback):
    ns = A["ns"]
    n = len(ns)
    sm, ss = c.slip_mkt_bps * 1e-4, c.slip_bps * 1e-4
    rows = o                                   # sorted by entry_i (stable) by the caller
    busy = -1
    out = []
    for r in rows.itertuples():
        T = int(r.entry_i)
        if T <= busy:
            continue
        s, lv, stop, xe = int(r.side), float(r.level), float(r.stop), int(r.exit_i)
        xe = xe if xe >= 0 else n
        t_end = ns[T] + (1 + N) * MIN_NS
        j = T + 1
        fill_i, fill_px = -1, np.nan
        while j < n and ns[j] < t_end and j < xe:
            if s > 0 and A["al"][j] <= lv:
                fill_i, fill_px = j, min(lv, A["ao"][j])
                break
            if s < 0 and A["bh"][j] >= lv:
                fill_i, fill_px = j, max(lv, A["bo"][j])
                break
            j += 1
        if fill_i < 0:
            w_last = j - 1
            if fallback:
                f = int(np.searchsorted(ns, t_end, side="left"))
                px = A["ao"][f] * (1 + sm) if s > 0 else A["bo"][f] * (1 - sm)
                if f < xe and f < n and s * (px - stop) > 0:
                    fill_i, fill_px = f, px
            if fill_i < 0:
                busy = max(busy, w_last)
                continue
        # manage the position with the rule's absolute stop; time exit at the open of xe (not on the fill bar)
        i = fill_i
        x_i, x_px, reason = -1, np.nan, ""
        while i < n:
            if i >= xe and i > fill_i:
                x_i, x_px, reason = i, (A["bo"][i] * (1 - sm) if s > 0 else A["ao"][i] * (1 + sm)), "time"
                break
            first = i == fill_i
            if s > 0 and A["bl"][i] <= stop:
                px = stop if first else min(stop, A["bo"][i])
                x_i, x_px, reason = i, px * (1 - ss), "stop"
                break
            if s < 0 and A["ah"][i] >= stop:
                px = stop if first else max(stop, A["ao"][i])
                x_i, x_px, reason = i, px * (1 + ss), "stop"
                break
            i += 1
        if x_i < 0:
            x_i, x_px, reason = n - 1, (A["bc"][n - 1] if s > 0 else A["ac"][n - 1]), "eod"
        et = pd.Timestamp(ns[fill_i], tz="UTC")
        xt = pd.Timestamp(ns[x_i], tz="UTC") + (pd.Timedelta(0) if reason == "time" else pd.Timedelta(minutes=1))
        d0 = trading_day(pd.DatetimeIndex([et])).values.astype("datetime64[D]")
        d1 = trading_day(pd.DatetimeIndex([xt - pd.Timedelta(seconds=1)])).values.astype("datetime64[D]")
        nights = int(np.busday_count(d0, d1)[0] + 2 * np.busday_count(d0, d1, weekmask=c.swap_triple)[0])
        swap = fill_px * (c.swap_long if s > 0 else c.swap_short) / 360.0 * nights
        pnl = s * (x_px - fill_px) - swap
        out.append({"entry_time": et, "exit_time": xt, "side": s, "R": pnl / abs(fill_px - stop),
                    "censored": x_i == n - 1})
        busy = x_i
    return pd.DataFrame(out)


def main():
    m1 = load_is("xauusd")
    A = arrays(m1)
    c = costs("xauusd", False)
    o = build_orders("orb_asia_2d_buf10", "xauusd", m1).sort_values("entry_i", kind="stable")
    cells = pd.read_parquet(os.path.join(RES, "cells", "orb_asia_2d_buf10__xauusd.parquet"))
    res = {}
    for cid, fb in (("RT30_mkt|price", True), ("RT30_skip|price", False)):
        mine = run(m1, A, o, c, 30, fb)
        eng = cells[(cells.cell == cid) & (cells.cost == "fp")]
        x = mine.merge(eng[["entry_time", "R"]], on="entry_time", how="outer", suffixes=("_loop", "_engine"),
                       indicator=True)
        both = x[x._merge == "both"]
        keep = ~mine.censored
        com = mine[keep & (mine.entry_time >= COMMON_START)]
        engc = eng[(~eng.censored) & (eng.entry_time >= COMMON_START)]
        res[cid] = {"trades_loop": int(len(mine)), "trades_engine": int(len(eng)),
                    "only_loop": int((x._merge == "left_only").sum()), "only_engine": int((x._merge == "right_only").sum()),
                    "max_abs_dR": float((both.R_loop - both.R_engine).abs().max()),
                    "common_n_loop": int(len(com)), "common_total_R_loop": round(float(com.R.sum()), 2),
                    "common_n_engine": int(len(engc)), "common_total_R_engine": round(float(engc.R.sum()), 2)}
        print(cid, res[cid], flush=True)
    jdump(res, os.path.join(RES, "selfcheck_orb.json"))


if __name__ == "__main__":
    main()
