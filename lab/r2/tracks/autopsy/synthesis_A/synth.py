"""Lead synthesis A (PROTOCOL_V3 Addendum H): the ten sleeves unchanged and with the five kept changes.  IN SAMPLE ONLY.

* Price frames are read with the parquet row filter ts < 2022-01-01 00:00 UTC (no 2022+ row is ever materialised);
  every rule and every simulation receives that slice explicitly (r2.run / recalc are never called on a full frame).
* Official trades and the lens's stored trades are read with entry_time < 2022-01-01 in the same call.
* nq_btc_follow: the us100 leader is registered from the in-sample us100 slice (set_leader) before any order is built.
* Costs: r2.costs(sym) on the stored FP frame (fp); spread x1.5 frame (apply_spread_mult) with r2.costs(sym, 1.5),
  orders rebuilt on it (stress) -- exactly r2.run's modes.
* Broker minimum: an order whose initial stop is closer than 3 x the spread of its fill bar is not sent.

    python3 synth.py run <sym>      runs of every sleeve of <sym> (unchanged + kept change), one trials.jsonl line each
"""
import json
import os
import sys
import time

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_synthesis_A")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

LAB = "/home/user/gold-orb/lab"
for _p in (LAB, os.path.join(LAB, "r2")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numba as nb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
MAIN0 = pd.Timestamp("2018-02-01", tz="UTC")
NY = "America/New_York"
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
TRIALS = os.path.join(HERE, "trials.jsonl")
CRYPTO = ("btcusd", "ethusd")

TEN = [("noise30", "us100"), ("ocm4", "us100"),
       ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
BY_SYM = {"us100": ["noise30", "ocm4"], "btcusd": ["brk72_24h_wd", "F1_brk_ridge_filter", "nq_btc_follow"],
          "ethusd": ["brk72_24h_wd", "F1_brk_ridge_filter"], "xauusd": ["GOLD_FRI_PM", "donch4h_stop", "orb_asia_2d_buf10"]}
# the five kept changes (declared.json, kept_changes)
CHANGE = {("ocm4", "us100"): "T1", ("F1_brk_ridge_filter", "ethusd"): "H2", ("brk72_24h_wd", "btcusd"): "S0.75r",
          ("donch4h_stop", "xauusd"): "S0.75r", ("orb_asia_2d_buf10", "xauusd"): "S0.75r"}
ABS_STOP = {"noise30", "orb_asia_2d_buf10"}     # rules whose stop is an absolute price


# ----------------------------------------------------------------------------------------- data
def load_is(sym):
    """In-sample M1 frame: rows with ts < 2022-01-01 00:00 UTC only (filter applied while reading)."""
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=[("ts", "<", CUT)])
    assert len(df) and df.index.max() < CUT and df.index.is_monotonic_increasing and df.index.is_unique
    return df


def load_official(name, sym):
    t = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"),
                        filters=[("entry_time", "<", CUT)])
    assert (t.entry_time < CUT).all()
    return t.sort_values("entry_time").reset_index(drop=True)


def load_lens_trades(name, sym, variant, mode):
    """Payoff lens's stored trades of one variant (reference = its reference file), in-sample rows only."""
    if variant == "ref":
        p = os.path.join(LAB, "results", "r2", "autopsy", "payoff", f"reference_{name}__{sym}.parquet")
    else:
        p = os.path.join(LAB, "results", "r2", "autopsy", "payoff", f"trades_{name}__{sym}.parquet")
    t = pd.read_parquet(p, filters=[("entry_time", "<", CUT)])
    assert (t.entry_time < CUT).all()
    if variant != "ref":
        t = t[t["variant"] == variant]
    t = t[t["mode"] == mode]
    return t.sort_values("entry_time").reset_index(drop=True)


_REG = None


def registry():
    """{(name, sym): (track, make_orders, params)} exactly as lab/r2/recalc.py registers the ten sleeves."""
    global _REG
    if _REG is None:
        import recalc
        out = {}
        for track, name, sym, mo, params in recalc.sleeves():
            if (name, sym) in TEN:
                out[(name, sym)] = (track, mo, params)
        assert len(out) == 10, sorted(out)
        _REG = out
    return _REG


def set_leader_is(us100_mid):
    _, mo, _ = registry()[("nq_btc_follow", "btcusd")]
    g = mo.__globals__
    g["clear_leaders"]()
    g["set_leader"]("us100", us100_mid)
    assert "us100" in g["_LEADERS"]


def clear_caches(mo):
    g = mo.__globals__
    for k in ("_cache", "_bar_cache", "_daily_cache"):
        if k in g and isinstance(g[k], dict):
            g[k].clear()


def build_orders(name, sym, m1):
    _, mo, params = registry()[(name, sym)]
    clear_caches(mo)
    o = mo(m1, **params).reset_index(drop=True)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    return o


def costs(sym, stress):
    return r2.costs(sym, 1.5 if stress else 1.0)


# ----------------------------------------------------------------------------------------- fills (as goldlab.sim._run)
@nb.njit(cache=True)
def _fills(bo, ao, bl, ah, al, bh, entry_i, side, etype, level, expiry_i, slip, slip_m):
    n = len(entry_i)
    N = len(bo)
    fb = np.full(n, -1, np.int64)
    fp = np.full(n, np.nan)
    for k in range(n):
        i0 = entry_i[k]
        if i0 < 0 or i0 >= N:
            continue
        s = side[k]
        if etype[k] == 0:
            fb[k] = i0
            fp[k] = ao[i0] * (1 + slip_m) if s > 0 else bo[i0] * (1 - slip_m)
            continue
        lv = level[k]
        jmax = min(expiry_i[k], N - 1)
        for i in range(i0, jmax + 1):
            if etype[k] == 1:
                if s > 0 and ah[i] >= lv:
                    fb[k] = i
                    fp[k] = max(lv, ao[i]) * (1 + slip)
                    break
                if s < 0 and bl[i] <= lv:
                    fb[k] = i
                    fp[k] = min(lv, bo[i]) * (1 - slip)
                    break
            else:
                if s > 0 and al[i] <= lv:
                    fb[k] = i
                    fp[k] = min(lv, ao[i])
                    break
                if s < 0 and bh[i] >= lv:
                    fb[k] = i
                    fp[k] = max(lv, bo[i])
                    break
    return fb, fp


def fills(m1, o, sym, stress):
    c = costs(sym, stress)
    n = len(o)
    col = lambda k, d: o[k].to_numpy() if k in o else np.full(n, d)
    return _fills(m1["bo"].to_numpy(np.float64), m1["ao"].to_numpy(np.float64), m1["bl"].to_numpy(np.float64),
                  m1["ah"].to_numpy(np.float64), m1["al"].to_numpy(np.float64), m1["bh"].to_numpy(np.float64),
                  o["entry_i"].to_numpy(np.int64), o["side"].to_numpy(np.int64),
                  col("etype", 0).astype(np.int64), col("level", np.nan).astype(np.float64),
                  col("expiry_i", -1).astype(np.int64), c.slip_bps * 1e-4,
                  (c.slip_mkt_bps if c.slip_mkt_bps >= 0 else c.slip_bps) * 1e-4)


def risk_and_spread(name, m1, o, sym, stress):
    """Fill bar, fill price, the rule's initial risk r0 (distance) and the spread of the fill bar, per order."""
    fb, fp = fills(m1, o, sym, stress)
    ok = fb >= 0
    j = np.clip(fb, 0, len(m1) - 1)
    spread = np.where(ok, m1["ao"].to_numpy()[j] - m1["bo"].to_numpy()[j], np.nan)
    if name in ABS_STOP:
        r0 = o["side"].to_numpy() * (fp - o["stop"].to_numpy())
    else:
        r0 = o["stop_dist"].to_numpy(float).copy()
    return fb, fp, r0, spread


def refused(d0, spread):
    """Broker minimum: a stop closer than 3 spreads of the fill bar is not sent (never-filled orders have no spread)."""
    return np.isfinite(spread) & (d0 < 3.0 * spread)


# ----------------------------------------------------------------------------------------- calendar helpers
def server_time(ts):
    return pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)


def ny_clock(dates, hh, mm):
    loc = pd.DatetimeIndex(dates).normalize() + pd.Timedelta(hours=hh, minutes=mm)
    return loc.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def bday(dates, j):
    return pd.DatetimeIndex(dates).normalize() + pd.offsets.BDay(int(j))


def friday_close_time(entry_ts):
    """Crypto: UTC time of the Friday 23:54 server bar of the server week of each entry (calendar value)."""
    srv = server_time(entry_ts)
    fri = srv.normalize() + pd.to_timedelta(4 - srv.dayofweek, unit="D") + pd.Timedelta(hours=23, minutes=54)
    return (fri - pd.Timedelta(hours=7)).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def exit_bar(m1, t):
    """Frame index of each trade's exit bar (exit_time = bar start for time exits, start + 1 min otherwise)."""
    et = t.exit_time - pd.to_timedelta(np.where(t.reason.to_numpy() == "time", 0, 1), unit="m")
    return np.searchsorted(m1.index.values, et.values.astype(m1.index.values.dtype), side="left")


def censored(m1, t, sym):
    """Trades still open when the in-sample frame ends (their result needs 2022 prices)."""
    if not len(t):
        return np.zeros(0, bool)
    if sym in CRYPTO:
        return (t.reason == "eod").to_numpy()
    xb = exit_bar(m1, t)
    return ((xb >= len(m1) - 1) & t.reason.isin(["time", "eod"]).to_numpy()) | (t.reason == "eod").to_numpy()


# ----------------------------------------------------------------------------------------- the kept changes
def change_T1(m1, O, r0, U):
    """ocm4 T1: no 15:55 exit; trail 1 x U from the best bid high / ask low since the fill (simulator trail);
    initial stop min(D, U) = D; time cap at the open of the first bar at/after 15:55 NY on the entry's NY date + 4
    business days (gl.exit_index), never earlier than the rule's own exit bar."""
    o = O.copy()
    ent_t = m1.index[np.clip(O["entry_i"].to_numpy(), 0, len(m1) - 1)]
    date = ent_t.tz_convert(NY).tz_localize(None).normalize()
    cap = gl.exit_index(m1, ny_clock(bday(date, 4), 15, 55))
    cap = np.maximum(np.asarray(cap, np.int64), O["exit_i"].to_numpy(np.int64))
    d0 = np.minimum(r0, 1.0 * U)
    o["stop_dist"] = d0
    o["trail"] = 1.0 * U
    o["exit_i"] = cap.astype(np.int64)
    return o, d0


def h2_decision(m1, O, sym, stress):
    """F1 H2: each order simulated alone with the rule's exits; True where the trade is still open at the close of
    the bar before its clock exit bar, leaves there by the clock, and is ahead by >= 1 x its initial risk on its exit
    side (bid close for a long, ask close for a short)."""
    t1 = simulate(m1, O, sym=sym, costs=costs(sym, stress), no_overlap=False)
    ahead = np.zeros(len(O), bool)
    if not len(t1):
        return ahead
    rows = t1.index.to_numpy()
    xb = exit_bar(m1, t1)
    xi = O["exit_i"].to_numpy()[rows]
    at_clock = (t1["reason"].to_numpy() == "time") & (xb == xi)
    c = np.clip(xb - 1, 0, len(m1) - 1)
    s = t1["side"].to_numpy()
    mark = np.where(s > 0, m1["bc"].to_numpy()[c], m1["ac"].to_numpy()[c])
    gain = s * (mark - t1["entry"].to_numpy())
    fbar = np.searchsorted(m1.index.values, t1.entry_time.values.astype(m1.index.values.dtype))
    ok = at_clock & (gain >= 1.0 * t1["risk"].to_numpy()) & (c >= fbar)
    ahead[rows[ok]] = True
    return ahead


def change_H2(m1, O, ahead):
    """F1 H2: where `ahead`, the exit moves to 15:55 NY on the decision's NY date + 2 business days, capped at the
    Friday 23:54 server bar of the entry's server week (gl.exit_index), never earlier than the rule's exit."""
    o = O.copy()
    tdec = pd.DatetimeIndex(pd.to_datetime(O["cid"].to_numpy(), utc=True))
    date = tdec.tz_convert(NY).tz_localize(None).normalize()
    ent_t = m1.index[np.clip(O["entry_i"].to_numpy(), 0, len(m1) - 1)]
    fri = gl.exit_index(m1, friday_close_time(ent_t))
    ext = np.minimum(np.asarray(gl.exit_index(m1, ny_clock(bday(date, 2), 15, 55)), np.int64), np.asarray(fri, np.int64))
    ext = np.maximum(ext, O["exit_i"].to_numpy(np.int64))
    o["exit_i"] = np.where(ahead, ext, O["exit_i"].to_numpy(np.int64)).astype(np.int64)
    return o


def change_S(name, O, r0, k):
    """Stop at k x the rule's distance from the fill, same money risk (R on the new stop); donch: trail scaled too."""
    o = O.copy()
    d0 = k * r0
    if name in ABS_STOP:
        o["stop"] = np.nan
    o["stop_dist"] = d0
    if name == "donch4h_stop":
        o["trail"] = k * O["trail"].to_numpy()
    return o, d0


def make_variant(name, sym, m1, O, stress, variant):
    """Orders to simulate (refused orders removed) for 'ref' (frozen rule) or the sleeve's kept change."""
    fb, fp, r0, spread = risk_and_spread(name, m1, O, sym, stress)
    info = {"orders": int(len(O))}
    if variant == "ref":
        o, d0 = O.copy(), r0
    elif variant == "T1":
        o, d0 = change_T1(m1, O, r0, O["stop_dist"].to_numpy(float) / 0.3)
    elif variant == "H2":
        ahead = h2_decision(m1, O, sym, stress)
        o, d0 = change_H2(m1, O, ahead), r0
        info["extended_orders"] = int(ahead.sum())
        o["ahead"] = ahead
    elif variant == "S0.75r":
        o, d0 = change_S(name, O, r0, 0.75)
    else:
        raise ValueError(variant)
    rf = refused(d0, spread)
    info["refused_orders"] = int(rf.sum())
    return o[~rf].reset_index(drop=True), info


def run_one(name, sym, m1, O, stress, variant):
    o, info = make_variant(name, sym, m1, O, stress, variant)
    t = simulate(m1, o, sym=sym, costs=costs(sym, stress), no_overlap=True)
    c = censored(m1, t, sym)
    info["censored"] = int(c.sum())
    t = t[~c].copy()
    return t, info


# ----------------------------------------------------------------------------------------- statistics
def stats(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0}
    pos, neg = R[R > 0], R[R < 0]
    cum = np.cumsum(R)
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    sd = float(R.std(ddof=1)) if n > 1 else float("nan")
    return {"n": n, "exp_R": round(float(R.mean()), 4), "win_rate": round(float((R > 0).mean()), 4),
            "avg_win_R": round(float(pos.mean()), 4) if len(pos) else 0.0,
            "avg_loss_R": round(float(neg.mean()), 4) if len(neg) else 0.0,
            "pf": round(float(pos.sum() / -neg.sum()), 3) if len(neg) else None,
            "total_R": round(float(R.sum()), 2), "sd_R": round(sd, 4),
            "mean_over_sd": round(float(R.mean() / sd), 4) if sd > 0 else None,
            "t_stat": round(float(R.mean() / (sd / np.sqrt(n))), 2) if sd > 0 else None,
            "max_dd_R_entry_order": round(dd, 2)}


def window(t, w):
    if w == "main":
        return t[(t.entry_time >= MAIN0) & (t.entry_time < CUT)]
    if w == "early":
        return t[t.entry_time < MAIN0]
    raise ValueError(w)


def by_year(t):
    return {int(y): {"n": int(len(g)), "total_R": round(float(g.R.sum()), 2), "exp_R": round(float(g.R.mean()), 4)}
            for y, g in t.groupby(t.entry_time.dt.year)}


def same_trades(a, b, tol=1e-9):
    """Trade-by-trade identity on entry/exit times, side, reason and R."""
    if len(a) != len(b):
        return False, f"n {len(a)} vs {len(b)}"
    a = a.sort_values(["entry_time", "side"]).reset_index(drop=True)
    b = b.sort_values(["entry_time", "side"]).reset_index(drop=True)
    for k in ("entry_time", "exit_time", "side", "reason"):
        if not (a[k].to_numpy() == b[k].to_numpy()).all():
            return False, f"column {k} differs on {int((a[k].to_numpy() != b[k].to_numpy()).sum())} trades"
    d = float(np.nanmax(np.abs(a["R"].to_numpy() - b["R"].to_numpy()))) if len(a) else 0.0
    return d <= tol, f"max |dR| {d:.2e}"


KEEP = ["oid", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R", "hold_min"]


def log(line):
    with open(TRIALS, "a") as f:
        f.write(json.dumps(line, default=str) + "\n")


# ----------------------------------------------------------------------------------------- driver
def run(sym):
    os.makedirs(WORK, exist_ok=True)
    m1 = load_is(sym)
    if sym == "btcusd":
        us = load_is("us100")
        set_leader_is(((us["bc"] + us["ac"]) / 2).rename("mid"))
        del us
    frames = {False: m1, True: apply_spread_mult(m1, 1.5)}
    rep = {}
    for name in BY_SYM[sym]:
        variants = ["ref"] + ([CHANGE[(name, sym)]] if (name, sym) in CHANGE else [])
        for stress in (False, True):
            fr = frames[stress]
            mode = "stress" if stress else "fp"
            t0 = time.time()
            O = build_orders(name, sym, fr)
            for variant in variants:
                t, info = run_one(name, sym, fr, O, stress, variant)
                line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": "simulation",
                        "sleeve": f"{name}:{sym}", "variant": variant, "mode": mode, **info,
                        "main": stats(window(t, "main").R), "early": stats(window(t, "early").R),
                        "by_year_main": by_year(window(t, "main"))}
                # rule 2: the pure frozen run (no refusal, no censoring) against the official rows
                if variant == "ref" and not stress:
                    tp = simulate(fr, O, sym=sym, costs=costs(sym, False), no_overlap=True)
                    off = load_official(name, sym)
                    cpure = censored(fr, tp, sym)
                    ok_all, msg_all = same_trades(tp[["entry_time", "exit_time", "side", "reason", "R"]],
                                                  off[["entry_time", "exit_time", "side", "reason", "R"]])
                    keep_off = ~off.entry_time.isin(tp.entry_time[cpure])
                    ok_unc, msg_unc = same_trades(tp[~cpure], off[keep_off])
                    line["rule2"] = {"official_n": int(len(off)), "official_total_R": round(float(off.R.sum()), 4),
                                     "mine_n": int(len(tp)), "mine_total_R": round(float(tp.R.sum()), 4),
                                     "identical_all": ok_all, "detail_all": msg_all,
                                     "censored_in_my_slice": int(cpure.sum()),
                                     "censored_entry_times": [str(x) for x in tp.entry_time[cpure]],
                                     "identical_without_censored": ok_unc, "detail_without_censored": msg_unc,
                                     "official_total_R_without_censored": round(float(off[keep_off].R.sum()), 4),
                                     "mine_total_R_without_censored": round(float(tp[~cpure].R.sum()), 4),
                                     "refusal_changes_trades": not same_trades(tp[~cpure], t)[0]}
                # cross-check against the payoff lens's stored trades of the same run
                try:
                    lt = load_lens_trades(name, sym, variant, mode)
                    ok, msg = same_trades(t[["entry_time", "exit_time", "side", "reason", "R"]],
                                          lt[["entry_time", "exit_time", "side", "reason", "R"]])
                    line["lens_crosscheck"] = {"identical": ok, "detail": msg, "lens_n": int(len(lt))}
                except Exception as e:  # noqa: BLE001
                    line["lens_crosscheck"] = {"error": repr(e)}
                log(line)
                cols = [c for c in KEEP + ["ahead"] if c in t.columns]
                t[cols].to_parquet(os.path.join(WORK, f"{name}__{sym}__{variant}__{mode}.parquet"))
                mm = line["main"]
                print(f"{name:20s} {sym} {variant:7s} {mode:6s} main n {mm['n']:5d} exp {mm['exp_R']:+.4f} "
                      f"tot {mm['total_R']:8.2f} | early n {line['early'].get('n', 0)} | refused {info['refused_orders']} "
                      f"cens {info['censored']} | lens {line['lens_crosscheck']} "
                      f"{'| rule2 ' + json.dumps({k: line['rule2'][k] for k in ('identical_all', 'identical_without_censored', 'mine_n', 'official_n', 'mine_total_R', 'official_total_R', 'refusal_changes_trades')}) if 'rule2' in line else ''}"
                      f" [{time.time() - t0:.0f}s]", flush=True)
                rep[(name, variant, mode)] = line
    return rep


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2])
