"""Null of the main configuration of night_fade (PROTOCOL_V3 Addendum L, section 4 basket null), IN SAMPLE ONLY (L27).

Same clock time, random day, same instrument: each main trade (base costs, the run's trades_01_main_base.parquet) is
re-entered on its cross, on an evening drawn uniformly with replacement among that cross's tradable evenings, at the open
of the first M1 bar at or after the New York clock time (hh:mm) of its entry bar; if that bar starts more than 5 minutes
late another evening is drawn (at most 20 draws, then the replay trade is dropped and counted). Same side; stop and
target distances as fractions of its entry fill, scaled by the replay bar's mid open; resting target (none if its fraction
is <= 0); time exit at 21:00 New York of the drawn evening (exit_index, 30-minute gap rule; dropped and counted if not
after the entry bar); base costs; every replay trade simulated (no_overlap=False). 200 replays, numpy default_rng(0).
Draw order: for each replay, for each cross in basket order, rng.integers(0, n_tradable_evenings, size=(n_trades, 20))
(trades by entry time; a trade uses the first of its 20 candidates that is at most 5 minutes late).
Statistic: pooled mean R of a replay; percentile = share of the 200 means strictly below the main's pooled mean R.
Outputs: results/r2/round6/night_fade/null.json, null_means.npy.

    python3 -I null.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

N_REPLAYS, SEED, MAX_DRAWS, MAX_LATE_MIN = 200, 0, 20, 5


def clock_min(entry_time):
    """New York minute of day of each entry bar."""
    ny = pd.DatetimeIndex(entry_time).tz_convert(C.NY)
    return (ny.hour * 60 + ny.minute).to_numpy(np.int64)


def replay_orders(bk, tr, cand, E, mid_ny0, x21, p):
    """Replay orders of one cross for one replay. tr: the cross's main trades (by entry time); cand: (n, MAX_DRAWS)
    indices into its tradable evenings E. Returns (orders, n_dropped_late, n_dropped_exit)."""
    n = len(tr)
    if n == 0:
        return pd.DataFrame(), 0, 0
    mod = clock_min(tr.entry_time)
    t_c = mid_ny0[cand] + mod[:, None] * C.NS_MIN                 # the clock time on each candidate evening
    N = len(bk.ns)
    ei = np.searchsorted(bk.ns, t_c, side="left")
    ok = (ei < N) & ((bk.ns[np.minimum(ei, N - 1)] - t_c) <= MAX_LATE_MIN * C.NS_MIN)
    has = ok.any(axis=1)
    pick = np.argmax(ok, axis=1)
    rows = np.arange(n)
    e_pick = cand[rows, pick]
    ent = ei[rows, pick]
    xi = x21[e_pick]
    keep = has & (xi > ent)
    side = tr.side.to_numpy(np.int64)
    fill = tr.entry.to_numpy(np.float64)
    stop_frac = tr.risk.to_numpy(np.float64) / fill
    tgt_frac = (tr.target_px.to_numpy(np.float64) - fill) * side / fill
    ec = np.minimum(ent, N - 1)
    mid_open = (bk.m1.bo.to_numpy()[ec] + bk.m1.ao.to_numpy()[ec]) / 2
    o = pd.DataFrame({"entry_i": ent, "side": side, "etype": 0, "stop_dist": stop_frac * mid_open,
                      "target_dist": np.where(tgt_frac > 0, tgt_frac * mid_open, np.nan), "exit_i": xi,
                      "evening": E[e_pick].to_numpy(), "cross": bk.cross, "src_entry_time": tr.entry_time.to_numpy()})[keep]
    if p["target_mode"] != "frozen_middle_band":
        raise ValueError("the null is declared for the main configuration (resting target)")
    return o.reset_index(drop=True), int((~has).sum()), int((has & ~(xi > ent)).sum())


def null_all(trades, crosses, load, p, n_replays=N_REPLAYS, seed=SEED, max_draws=MAX_DRAWS):
    """The null on the pooled main trades (column 'cross'); frames from load(cross), one cross in memory at a time."""
    trades = trades.sort_values(["entry_time", "cross"], kind="stable").reset_index(drop=True)
    main_mean = float(trades.R.mean())
    per = {c: trades[trades.cross == c].sort_values("entry_time", kind="stable").reset_index(drop=True) for c in crosses}
    E = {}
    for c in crosses:                                              # pass 1: tradable evenings of each cross
        bk = C.Book(load(c), c)
        E[c] = bk.tradable(int(p["h1_bars"]))
        del bk
    rng = np.random.default_rng(seed)                              # pass 2: every draw, in the declared order
    draws = {c: np.empty((n_replays, len(per[c]), max_draws), np.int32) for c in crosses}
    for r in range(n_replays):
        for c in crosses:
            if len(per[c]):
                draws[c][r] = rng.integers(0, len(E[c]), size=(len(per[c]), max_draws))
    sums = np.zeros(n_replays)
    cnts = np.zeros(n_replays, np.int64)
    d_late = np.zeros(n_replays, np.int64)
    d_exit = np.zeros(n_replays, np.int64)
    cst = C.costs(p)
    for c in crosses:                                              # pass 3: replays, one cross at a time
        if len(per[c]) == 0:
            continue
        bk = C.Book(load(c), c)
        mid0 = C.ny_utc_ns(E[c], "00:00")                          # New York midnight of each evening (same offset all evening)
        x21 = bk.exit_at(E[c], p["time_exit_ny"], int(p["exit_gap_max_min"]))
        for r in range(n_replays):
            o, nl, nx = replay_orders(bk, per[c], draws[c][r], E[c], mid0, x21, p)
            d_late[r] += nl
            d_exit[r] += nx
            if len(o) == 0:
                continue
            t = C.run_orders(bk, o, cst, no_overlap=False, check=False)
            C.check_trades(t, last_entry_ny="20:05")
            assert len(t) == len(o)
            sums[r] += float(t.R.sum())
            cnts[r] += len(t)
        del bk
    means = sums / np.maximum(cnts, 1)
    pct = float((means < main_mean).mean() * 100)
    out = {"what": "basket null of the main (same clock time, random tradable evening, same cross), Addendum L",
           "n_replays": n_replays, "seed": seed, "max_draws": max_draws, "no_overlap": False,
           "main_n": int(len(trades)), "main_mean_R": round(main_mean, 6),
           "null_mean_R": round(float(means.mean()), 6), "null_sd_R": round(float(means.std(ddof=1)), 6) if n_replays > 1 else None,
           "null_p50_R": round(float(np.percentile(means, 50)), 6), "null_p975_R": round(float(np.percentile(means, 97.5)), 6),
           "null_max_R": round(float(means.max()), 6), "percentile": round(pct, 2), "percentile_raw": pct,
           "main_mean_R_raw": main_mean, "pass": bool(pct >= 97.5),
           "replay_trades_min_max": [int(cnts.min()), int(cnts.max())],
           "dropped_after_20_late_draws_mean": round(float(d_late.mean()), 3),
           "dropped_exit_not_after_entry_mean": round(float(d_exit.mean()), 3),
           "tradable_evenings": {c: int(len(E[c])) for c in crosses}}
    return out, means


def main():
    decl, sha = C.declared()
    C.check_frames(decl)
    p = decl["configurations"][0]["params"]
    assert decl["configurations"][0]["name"] == "main"
    crosses = decl["crosses_kept"]
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main_base.parquet"))
    assert (t.entry_time < C.CUT).all() and (t.exit_time < C.CUT).all()
    t0 = time.time()
    out, means = null_all(t, crosses, C.load_base, p)
    out.update({"declared_sha256": sha, "seconds": round(time.time() - t0, 1)})
    np.save(os.path.join(C.OUT, "null_means.npy"), means)
    C.jdump(out, os.path.join(C.OUT, "null.json"))
    print(out)


if __name__ == "__main__":
    main()
