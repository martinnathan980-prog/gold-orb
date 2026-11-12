"""Round 4 (PROTOCOL_V3 Addendum J), rule 2: FX weekend overreaction fade, eight G10 pairs as one basket.

The rule, exactly as frozen in lab/results/r2/round4_ideas.json judge.ranking[1], with the readings declared in
lab/results/r2/round4/fx_weekend/declared.json (written before any frame was read):

  F  = mid open of the first M1 bar starting in [Friday 16:50, 17:05) NY        (none -> pair skipped that weekend)
  D  = Sunday `dec` NY (20:00 main); P = mid open of the first M1 bar starting in [D, D+15 min)   (none -> skipped)
  sigma = sd (ddof 1) of the last 60 log returns of daily mid closes (lab trading days ending 17:00 NY,
          goldlab.full_days), days complete at D only (the last one ends Friday 17:00)
  z  = ln(P/F)/sigma;  signal if |z| >= percentile q (numpy, linear) of the pair's |z| over its previous 104 weekends
       with a z (>= 52 needed);  side = -sign(z)
  entry: market at the open of the M1 bar AFTER the P bar (P is that bar's open: the fill is never the decision tick),
         which must start by D + 15 min
  stop : stop_atr x ATR(20) (goldlab.atr, Wilder, daily full days, Friday's value), from the fill; refused if closer
         than 3 spreads of the entry bar
  exit : market at Monday 16:00 NY (Tuesday 12:00 / Wednesday 12:00 for neighbours) via goldlab.exit_index

IN SAMPLE ONLY: every frame is read with the pyarrow filter ts < 2022-01-01 (load_is) and passed explicitly.
"""
import json
import math
import os
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR",
                      "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/fxwk_numba")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

RES = os.path.join(LAB, "results", "r2", "round4", "fx_weekend")
IS_END = pd.Timestamp("2022-01-01", tz="UTC")       # nothing at or after this instant is ever read
NY = "America/New_York"
PAIRS = ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"]
M = np.timedelta64(1, "m")
EXITS = {"mon16": (1, "16:00"), "tue12": (2, "12:00"), "wed12": (3, "12:00")}
TOL = 15 * M                                         # tolerance for the F, P and entry bars


# ------------------------------------------------------------------------------------------------ data
def load_is(sym):
    """In-sample M1 frame (bar start < 2022-01-01 00:00 UTC), filtered while reading: no 2022+ row exists in memory."""
    path = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.max() < IS_END
    return df


def naive_utc(m1):
    return m1.index.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")


def wall(dates, add_days, hhmm):
    """New York wall-clock time `hhmm` on (naive calendar dates + add_days), as naive UTC datetime64[ns]."""
    h, mm = (int(x) for x in hhmm.split(":"))
    loc = pd.DatetimeIndex(dates) + pd.Timedelta(days=add_days, hours=h, minutes=mm)
    return loc.tz_localize(NY, nonexistent="shift_forward", ambiguous=False).tz_convert("UTC").tz_localize(None) \
        .values.astype("datetime64[ns]")


def sundays(m1):
    """Every calendar Sunday (New York date) covered by the frame, as naive dates."""
    a = m1.index[0].tz_convert(NY).tz_localize(None).normalize()
    b = m1.index[-1].tz_convert(NY).tz_localize(None).normalize()
    d = pd.date_range(a, b, freq="D")
    return d[d.dayofweek == 6]


def daily_table(m1):
    """Full trading days (ending 17:00 NY): their completion time, sigma(60 log returns) and Wilder ATR(20), mid."""
    d = gl.full_days(m1)
    c = d["c"].to_numpy(float)
    lr = np.r_[np.nan, np.log(c[1:] / c[:-1])]
    sig = pd.Series(lr).rolling(60).std(ddof=1).to_numpy()
    atr = gl.atr(d, 20).to_numpy(float)
    tc = pd.DatetimeIndex(d["t_close"]).tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
    return tc, sig, atr


# ------------------------------------------------------------------------------------------------ rule
def decisions(m1, dec="20:00", q=75, daily=None):
    """One row per calendar Sunday: every quantity of the decision, known at the open of the P bar."""
    idx = naive_utc(m1)
    N = len(idx)
    mo = ((m1["bo"].to_numpy(float) + m1["ao"].to_numpy(float)) / 2)
    S = sundays(m1)
    tF = wall(S, -2, "16:50")
    tD = wall(S, 0, dec)
    jF = np.searchsorted(idx, tF, side="left")
    okF = (jF < N) & (idx[np.minimum(jF, N - 1)] < tF + TOL)
    jP = np.searchsorted(idx, tD, side="left")
    okP = (jP < N) & (idx[np.minimum(jP, N - 1)] < tD + TOL)
    jE = jP + 1
    okE = okP & (jE < N) & (idx[np.minimum(jE, N - 1)] <= tD + TOL)
    tc, sig, atr = daily if daily is not None else daily_table(m1)
    k = np.searchsorted(tc, tD, side="right") - 1          # last full day complete at D (t_close <= D)
    okK = k >= 0
    kk = np.maximum(k, 0)
    sigma = np.where(okK, sig[kk], np.nan)
    atr_d = np.where(okK, atr[kk], np.nan)
    F = np.where(okF, mo[np.minimum(jF, N - 1)], np.nan)
    P = np.where(okP, mo[np.minimum(jP, N - 1)], np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.log(P / F) / sigma
    valid = okF & okP & np.isfinite(z) & (sigma > 0)
    az = np.abs(z)
    thr = np.full(len(S), np.nan)
    nh = np.zeros(len(S), np.int64)
    vz = np.flatnonzero(valid)
    for r, i in enumerate(vz):
        prev = az[vz[max(0, r - 104):r]]
        nh[i] = len(prev)
        if len(prev) >= 52:
            thr[i] = float(np.percentile(prev, q))
    decided = valid & np.isfinite(thr)
    signal = decided & (az >= thr) & (z != 0)
    side = np.where(signal, -np.sign(np.nan_to_num(z)), 0).astype(np.int64)
    return pd.DataFrame({
        "sunday": S, "t_dec": tD, "jF": np.where(okF, jF, -1), "F": F, "jP": np.where(okP, jP, -1), "P": P,
        "t_P": np.where(okP, idx[np.minimum(jP, N - 1)], np.datetime64("NaT")),
        "jE": np.where(okE, jE, -1), "okE": okE, "k_day": np.where(okK, k, -1),
        "t_day": np.where(okK, tc[kk], np.datetime64("NaT")), "sigma": sigma, "atr": atr_d,
        "z": z, "absz": az, "n_hist": nh, "thr": thr, "decided": decided, "signal": signal, "side": side})


def exit_bars(m1, dtab, exit="mon16"):
    add, hhmm = EXITS[exit]
    tX = wall(dtab["sunday"], add, hhmm)
    return gl.exit_index(m1, pd.DatetimeIndex(tX).tz_localize("UTC")), tX


def make_orders(m1, dec="20:00", q=75, exit="mon16", stop_atr=1.0, dtab=None, daily=None, min_spreads=3.0):
    """Orders of one configuration on the frame given (fp or widened quotes)."""
    if dtab is None:
        dtab = decisions(m1, dec=dec, q=q, daily=daily)
    xi, tX = exit_bars(m1, dtab, exit)
    jE = dtab["jE"].to_numpy()
    atr = dtab["atr"].to_numpy(float)
    ok = dtab["signal"].to_numpy() & dtab["okE"].to_numpy() & np.isfinite(atr) & (atr > 0) & (xi > jE)
    o = pd.DataFrame({
        "entry_i": jE.astype(np.int64), "side": dtab["side"].to_numpy(np.int64), "etype": 0,
        "stop_dist": float(stop_atr) * atr, "exit_i": xi.astype(np.int64),
        "sunday": dtab["sunday"].to_numpy(), "z": dtab["z"].to_numpy(float), "thr": dtab["thr"].to_numpy(float),
        "F": dtab["F"].to_numpy(float), "P": dtab["P"].to_numpy(float), "sigma": dtab["sigma"].to_numpy(float),
        "atr": atr, "jP": dtab["jP"].to_numpy(np.int64), "sched_exit": pd.DatetimeIndex(tX).tz_localize("UTC")})[ok]
    o = o.reset_index(drop=True)
    spr = (m1["ao"].to_numpy(float) - m1["bo"].to_numpy(float))[o["entry_i"].to_numpy()]
    bad = o["stop_dist"].to_numpy() < min_spreads * spr
    o = o[~bad].reset_index(drop=True)
    o.attrs["refused_3spreads"] = int(bad.sum())
    o.attrs["signals"] = int(dtab["signal"].sum())
    o.attrs["decided"] = int(dtab["decided"].sum())
    return o


def run_config(m1, sym, params, mode="fp", daily=None, dtab=None, no_overlap=True):
    """Simulate one configuration on one pair. mode 'fp' (FP costs) or 'stress' (spread and slippage x1.5, orders
    rebuilt on the widened quotes)."""
    mk = m1 if mode == "fp" else apply_spread_mult(m1, 1.5)
    c = r2.costs(sym) if mode == "fp" else r2.costs(sym, 1.5)
    o = make_orders(mk, dtab=dtab, daily=daily, **params)
    if not len(o):
        return pd.DataFrame(), o
    t = simulate(mk, o, sym=sym, costs=c, no_overlap=no_overlap)
    t = t[t.entry_time < IS_END].copy()
    t["sym"] = sym
    t.attrs["refused_3spreads"] = o.attrs["refused_3spreads"]
    return t, o


# ------------------------------------------------------------------------------------------------ statistics
def _pf(R):
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else (float("inf") if g > 0 else float("nan"))


def usd_side(sym, side):
    base, quote = sym[:3], sym[3:]
    if quote == "usd":
        return -side
    if base == "usd":
        return side
    return 0


def small(T):
    """Compact statistics of any group of trades."""
    if T is None or not len(T):
        return {"n": 0}
    R = T["R"].to_numpy(float)
    return {"n": int(len(R)), "pf": round(_pf(R), 3), "expectancy_R": round(float(R.mean()), 4),
            "total_R": round(float(R.sum()), 1), "win_rate": round(float((R > 0).mean()), 3),
            "t_trades": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 2) if len(R) > 2 else None,
            "bps_per_trade": round(float((T["pnl"] / T["entry"]).mean() * 1e4), 2)}


def pooled(T, pairs=PAIRS):
    """PROTOCOL_V3 s.4 basket statistics on pooled trades (column `sym`)."""
    if T is None or not len(T):
        return {"n": 0}
    R = T["R"].to_numpy(float)
    td = gl.trading_day(T.entry_time)
    daily = T.groupby(td)["R"].sum()
    yrs = T.groupby(T.entry_time.dt.year)["R"].sum()
    by_sym = T.groupby("sym")["R"].agg(["count", "mean", "sum"]).reindex(pairs)
    tot = float(R.sum())
    wk = T.groupby(T.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    wk_all = wk.reindex(pd.period_range(wk.index.min(), wk.index.max(), freq="W"), fill_value=0.0)
    hold_h = T["hold_min"].to_numpy(float) / 60
    present = by_sym["count"].fillna(0) > 0
    out = {
        "n": int(len(R)), "pf": round(_pf(R), 3), "expectancy_R": round(float(R.mean()), 4), "total_R": round(tot, 1),
        "win_rate": round(float((R > 0).mean()), 3),
        "avg_win_R": round(float(R[R > 0].mean()), 3) if (R > 0).any() else 0.0,
        "avg_loss_R": round(float(R[R < 0].mean()), 3) if (R < 0).any() else 0.0,
        "t_trades": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 3),
        "t_daily": round(float(daily.mean() / (daily.std(ddof=1) / math.sqrt(len(daily)))), 3),
        "n_days": int(len(daily)), "mean_daily_sum_R": round(float(daily.mean()), 4),
        "years_pos": f"{int((yrs > 0).sum())}/{len(yrs)}",
        "by_year_R": {int(k): round(float(v), 1) for k, v in yrs.items()},
        "by_year_n": {int(k): int(v) for k, v in T.groupby(T.entry_time.dt.year).size().items()},
        "pairs_pos": f"{int((by_sym['mean'] > 0).sum())}/{int(present.sum())}",
        "max_pair_share": round(float(by_sym["sum"].max() / tot), 3) if tot > 0 else None,
        "by_pair": {s: {"n": int(r["count"]) if np.isfinite(r["count"]) else 0,
                        "exp_R": None if not np.isfinite(r["mean"]) else round(float(r["mean"]), 4),
                        "total_R": None if not np.isfinite(r["sum"]) else round(float(r["sum"]), 1)}
                    for s, r in by_sym.iterrows()},
        "long_n": int((T.side > 0).sum()), "long_R": round(float(T.loc[T.side > 0, "R"].sum()), 1),
        "short_n": int((T.side < 0).sum()), "short_R": round(float(T.loc[T.side < 0, "R"].sum()), 1),
        "bps_per_trade": round(float((T["pnl"] / T["entry"]).mean() * 1e4), 2),
        "avg_hold_h": round(float(hold_h.mean()), 2), "max_hold_h": round(float(hold_h.max()), 2),
        "exit_reasons": {str(k): int(v) for k, v in T["reason"].value_counts().items()},
        "swap_total_price_share_bp": round(float((T["swap"] / T["entry"]).mean() * 1e4), 3),
        "weeks_pos_pct": round(float((wk_all > 0).mean() * 100), 1),
        "first_entry": str(T.entry_time.min()), "last_entry": str(T.entry_time.max()),
        "last_exit": str(T.exit_time.max()),
    }
    return out


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=_js, ensure_ascii=False)


def _js(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return str(x)
    return str(x)
