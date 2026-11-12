"""Addendum H, lens `entry`, part 1 -- what happens right after the signal (description, in sample, FP costs).

On my reproduced official trades (results/r2/autopsy/entry/baseline/, identical to the official in-sample rows):
  (a) path of the price over the first 1, 2, 5, 15, 30, 60 minutes, in R, relative to the lab's entry price
      (mark-to-market on the closing quote: bid close for a long, ask close for a short, at the close of the last bar
      that started before fill time + t);
  (b) how often the price comes back to the entry price and to a price better by 0.1, 0.25, 0.5 R before the trade is
      decided (entry-side quote: ask low for a long, bid high for a short; from the fill bar for market entries, from
      the next bar for stop/limit fills; up to the exit bar for stop exits, the bar before the exit for time exits);
  (c) what entering 1, 2 or 5 minutes late costs or saves (each official trade re-run alone, exits unchanged, the set
      of trades held fixed; stop at the rule's price S0 or at the rule's distance D);
  (d) whether the first minutes go the trade's way more often for the trades that end in gain.
Windows: common (entries 2018-02-01..2021-12-31) and pre (earlier in-sample entries), censored trades left out.
"""
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (A_COLS_LEADER, COMMON_START, MIN_NS, ORDER, RES, arrays, build_orders, costs, jdump,  # noqa
                    jline, key, lab_orders, load_is, nb, np, pd, sim_legs)

T_PATH = (1, 2, 5, 15, 30, 60)
KS = np.array([0.0, 0.10, 0.25, 0.50])
DELAYS = (1, 2, 5)
T_FIRST = (1, 2, 5, 15)
WIN = ("common", "pre")


@nb.njit(cache=True)
def _comeback(al, bh, j0, j1, side, entry, risk, ks):
    n = len(j0)
    m = len(ks)
    first = np.full((n, m), -1, np.int64)
    for t in range(n):
        left = m
        for j in range(j0[t], j1[t] + 1):
            for q in range(m):
                if first[t, q] >= 0:
                    continue
                lvl = entry[t] - side[t] * ks[q] * risk[t]
                hit = al[j] <= lvl if side[t] > 0 else bh[j] >= lvl
                if hit:
                    first[t, q] = j
                    left -= 1
            if left == 0:
                break
    return first


@nb.njit(cache=True)
def _touched_between(bl, ah, a, b, side, stop):
    """True where the stop price was touched on a bar in [a, b] (long: bid low <= stop; short: ask high >= stop)."""
    n = len(a)
    out = np.zeros(n, np.bool_)
    for t in range(n):
        for j in range(a[t], b[t] + 1):
            if (side[t] > 0 and bl[j] <= stop[t]) or (side[t] < 0 and ah[j] >= stop[t]):
                out[t] = True
                break
    return out


def q(x, p):
    return round(float(np.quantile(x, p)), 4) if len(x) else None


def mean(x):
    return round(float(np.mean(x)), 4) if len(x) else None


def anatomy_one(name, sym, m1, A, leader, trial_lines):
    tr = pd.read_parquet(os.path.join(RES, "baseline", f"{name}__{sym}.parquet"))
    N = len(A["ns"])
    tr = tr[tr.xi < N - 1].reset_index(drop=True)              # censored trade(s) out
    o = build_orders(name, sym, m1, leader)
    lo = lab_orders(o)
    row = tr.order_row.to_numpy(np.int64)
    etype = lo.etype.to_numpy()[row]
    exit_i = lo.exit_i.to_numpy()[row]
    trail = lo.trail.to_numpy(float)[row]
    ns = A["ns"]
    fill_ns = tr.entry_time.dt.as_unit("ns").astype("int64").to_numpy()
    fi = tr.fi.to_numpy(np.int64)
    xi = tr.xi.to_numpy(np.int64)
    side = tr.side.to_numpy(np.int64)
    entry = tr.entry.to_numpy(float)
    risk = tr.risk.to_numpy(float)
    R = tr.R.to_numpy(float)
    stop = tr.stop.to_numpy(float)
    reason = tr.reason.to_numpy(object)
    win = R > 0
    w_common = (tr.entry_time >= COMMON_START).to_numpy()
    masks = {"common": w_common, "pre": ~w_common}
    spread_R = (A["ao"][fi] - A["bo"][fi]) / risk

    # (a) path and (d) first minutes
    U = {}
    closed = {}
    for t in T_PATH:
        d = np.searchsorted(ns, fill_ns + t * MIN_NS, side="left") - 1
        qte = np.where(side > 0, A["bc"][d], A["ac"][d])
        U[t] = side * (qte - entry) / risk
        closed[t] = xi <= d
    path_rows, first_rows = [], []
    for wname, msk in masks.items():
        if msk.sum() == 0:
            continue
        for t in T_PATH:
            u = U[t][msk]
            path_rows.append({"sleeve": key(name, sym), "window": wname, "t_min": t, "n": int(msk.sum()),
                              "mean_u_R": mean(u), "median_u_R": q(u, .5), "p10_u_R": q(u, .1), "p25_u_R": q(u, .25),
                              "p75_u_R": q(u, .75), "p90_u_R": q(u, .9), "share_u_pos": mean(u > 0),
                              "share_closed": mean(closed[t][msk]), "mean_u_winners": mean(U[t][msk & win]),
                              "mean_u_losers": mean(U[t][msk & ~win]),
                              "median_spread_R_at_entry": q(spread_R[msk], .5)})
        for t in T_FIRST:
            u = U[t]
            mw, ml = msk & win, msk & ~win
            pos = msk & (u > 0)
            neg = msk & (u <= 0)
            lossR = R[ml].sum()
            first_rows.append({
                "sleeve": key(name, sym), "window": wname, "t_min": t, "n_winners": int(mw.sum()),
                "n_losers": int(ml.sum()), "p_up_winners": mean(u[mw] > 0), "p_up_losers": mean(u[ml] > 0),
                "diff_pp": round(100 * (float(np.mean(u[mw] > 0)) - float(np.mean(u[ml] > 0))), 1)
                if mw.sum() and ml.sum() else None,
                "mean_u_winners": mean(u[mw]), "mean_u_losers": mean(u[ml]),
                "n_up": int(pos.sum()), "meanR_if_up": mean(R[pos]), "n_not_up": int(neg.sum()),
                "meanR_if_not_up": mean(R[neg]), "totalR_if_up": round(float(R[pos].sum()), 2),
                "totalR_if_not_up": round(float(R[neg].sum()), 2),
                "share_of_loss_R_from_not_up_start": round(float(R[ml & (u <= 0)].sum() / lossR), 4)
                if lossR < 0 else None})

    # (b) come-backs before the trade is decided.  'fill_bar': market entries from their own fill bar (filled at its
    # open, so the rest of that minute counts; note the lab's market fill is the ask/bid open plus slippage, so
    # k = 0 is met at once whenever the minute trades through its open); 'next_bar': every trade from the bar after
    # its fill bar (stop and limit fills always start there: their fill is inside the bar).
    stop_like = np.isin(reason, ["stop", "trail", "gap", "eod"])
    j1 = np.where(stop_like, xi, xi - 1).astype(np.int64)
    cb_rows = []
    for start in ("fill_bar", "next_bar"):
        j0 = (np.where(etype == 0, fi, fi + 1) if start == "fill_bar" else fi + 1).astype(np.int64)
        first = _comeback(A["al"], A["bh"], j0, j1, side, entry, risk, KS)
        for wname, msk in masks.items():
            if msk.sum() == 0:
                continue
            for qi, kk in enumerate(KS):
                hit = first[:, qi] >= 0
                mins = np.where(hit, (ns[np.maximum(first[:, qi], 0)] - fill_ns) / MIN_NS, np.nan)
                rowd = {"sleeve": key(name, sym), "window": wname, "scan_from": start, "k_R": float(kk),
                        "n": int(msk.sum()), "n_winners": int((msk & win).sum()), "n_losers": int((msk & ~win).sum()),
                        "share_all": mean(hit[msk]), "share_winners": mean(hit[msk & win]),
                        "share_losers": mean(hit[msk & ~win]),
                        "median_min_to_touch": q(mins[msk & hit], .5) if (msk & hit).sum() else None}
                for lim in (5, 15, 60):
                    within = hit & (mins < lim)
                    rowd[f"within_{lim}m_all"] = mean(within[msk])
                    rowd[f"within_{lim}m_winners"] = mean(within[msk & win])
                    rowd[f"within_{lim}m_losers"] = mean(within[msk & ~win])
                rowd["meanR_touched"] = mean(R[msk & hit])
                rowd["meanR_not_touched"] = mean(R[msk & ~hit])
                rowd["totalR_not_touched"] = round(float(R[msk & ~hit].sum()), 2)
                cb_rows.append(rowd)

    # (c) late entries: each official trade alone, market at fill + d minutes, exits unchanged
    c = costs(sym, False)
    sm = c.slip_mkt_bps * 1e-4
    late_rows = []
    for d in DELAYS:
        f = np.searchsorted(ns, fill_ns + d * MIN_NS, side="left").astype(np.int64)
        f_ok = (f < N) & (f < np.where(exit_i >= 0, exit_i, N))
        fc = np.minimum(f, N - 1)
        p_late = np.where(side > 0, A["ao"][fc] * (1 + sm), A["bo"][fc] * (1 - sm))
        drift = side * (p_late - entry) / risk
        touched = _touched_between(A["bl"], A["ah"], fi, np.maximum(fc - 1, fi), side, stop) & (fc > fi)
        beyond = side * (p_late - stop) <= 0
        void_price = ~f_ok | touched | beyond
        void_dist = ~f_ok
        res = {}
        for mode, void in (("price", void_price), ("dist", void_dist)):
            keep = np.where(~void)[0]
            legs = pd.DataFrame({"entry_i": f[keep], "side": side[keep], "etype": 0, "level": np.nan,
                                 "expiry_i": -1, "stop": stop[keep] if mode == "price" else np.nan,
                                 "stop_dist": np.nan if mode == "price" else risk[keep], "target": np.nan,
                                 "target_dist": np.nan, "exit_i": exit_i[keep], "trail": trail[keep], "be": np.nan})
            r = sim_legs(m1, A, legs, sym, False)
            Rl = np.zeros(len(tr))
            ok = r.filled.to_numpy() & ~r.refused.to_numpy()
            Rl[keep[ok]] = r.R.to_numpy(float)[ok]
            res[mode] = (Rl, void | ~np.isin(np.arange(len(tr)), keep[ok]))
            trial_lines.append({"part": "part1", "sleeve": key(name, sym), "what": f"late entry +{d} min",
                                "stop_mode": mode, "n_trades_fixed": int(len(tr)), "n_void": int(res[mode][1].sum()),
                                "totalR_common_late": round(float(Rl[w_common].sum()), 2),
                                "totalR_common_orig": round(float(R[w_common].sum()), 2),
                                "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")})
        for wname, msk in masks.items():
            if msk.sum() == 0:
                continue
            stopped_before = msk & touched & stop_like & (xi < fc)
            late_rows.append({
                "sleeve": key(name, sym), "window": wname, "delay_min": d, "n": int(msk.sum()),
                "drift_mean_R": mean(drift[msk & f_ok]), "drift_median_R": q(drift[msk & f_ok], .5),
                "drift_mean_R_winners": mean(drift[msk & f_ok & win]),
                "drift_mean_R_losers": mean(drift[msk & f_ok & ~win]),
                "totalR_orig": round(float(R[msk].sum()), 2),
                "totalR_late_price": round(float(res["price"][0][msk].sum()), 2),
                "void_price": int(res["price"][1][msk].sum()),
                "totalR_late_dist": round(float(res["dist"][0][msk].sum()), 2),
                "void_dist": int(res["dist"][1][msk].sum()),
                "meanR_orig": mean(R[msk]), "meanR_late_dist_nonvoid": mean(res["dist"][0][msk & ~res["dist"][1]]),
                "orig_stopped_before_late_entry": int(stopped_before.sum()),
                "orig_R_of_those": round(float(R[stopped_before].sum()), 2)})
    return path_rows, cb_rows, late_rows, first_rows


def main():
    t00 = time.time()
    trial_lines = []
    P, C, L, F = [], [], [], []
    cur = None
    m1 = A = leader = None
    for name, sym in ORDER:
        t0 = time.time()
        if sym != cur:
            m1 = A = leader = None
            m1 = load_is(sym)
            A = arrays(m1)
            leader = load_is("us100", cols=A_COLS_LEADER) if sym == "btcusd" else None
            cur = sym
        p, cb, la, fm = anatomy_one(name, sym, m1, A, leader, trial_lines)
        P += p
        C += cb
        L += la
        F += fm
        print(f"{name:20s} {sym:7s} done [{time.time() - t0:.1f}s]", flush=True)
    pd.DataFrame(P).to_csv(os.path.join(RES, "anatomy_path.csv"), index=False)
    pd.DataFrame(C).to_csv(os.path.join(RES, "anatomy_comeback.csv"), index=False)
    pd.DataFrame(L).to_csv(os.path.join(RES, "anatomy_late.csv"), index=False)
    pd.DataFrame(F).to_csv(os.path.join(RES, "anatomy_first_minutes.csv"), index=False)
    jdump({"what": "part 1 anatomy (description), FP costs, censored trades left out",
           "path": P, "comeback": C, "late": L, "first_minutes": F},
          os.path.join(RES, "anatomy.json"))
    with open(os.path.join(RES, "trials.jsonl"), "a") as fh:
        for ln in trial_lines:
            fh.write(jline(ln) + "\n")
    print(f"total {time.time() - t00:.0f}s", flush=True)


if __name__ == "__main__":
    main()
