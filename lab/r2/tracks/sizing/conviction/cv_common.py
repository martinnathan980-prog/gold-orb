"""Lens `conviction` (PROTOCOL_V3, Addendum I): a stake per trade from what is known at the decision.
IN SAMPLE ONLY. Shared helpers.

Data rules
- Price frames: read with the parquet row filter ts < 2022-01-01 (through the context lens's loaders, which assert it),
  and only those slices are given to the rules and to the simulator.
- Official trades: read with the filter entry_time < 2022-01-01 in the same statement.
- Signals / chains: the context lens's in-sample tables (results/r2/autopsy/context/{signals,chains}), built from the
  same in-sample slices; read as they are (no 2022+ row exists in them; asserted).
- Nothing here writes outside lab/r2/tracks/sizing/conviction/ and lab/results/r2/sizing/conviction/.

The account: the PLAIN SUM of the ten sleeves' one-position chains (no position caps), 1 R per trade times the
variant's stake multiplier, no compounding. Kept the same throughout.
Weeks: FP server weeks (New York + 7 h, Monday..Sunday); a trade's stake x R is booked in the week of its EXIT time;
every calendar week counts (empty weeks = 0). Out-of-fold window: the server weeks whose Thursday falls in 2019, 2020
or 2021 (Mondays 2018-12-31 .. 2021-12-27, 157 weeks); a week belongs to the year of its Thursday.

Run with:  NUMBA_CACHE_DIR=/tmp/conviction_numba PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
"""
import json
import os
import sys

if not os.environ.get("NUMBA_CACHE_DIR", "").startswith("/tmp"):
    raise SystemExit("set NUMBA_CACHE_DIR to a directory under /tmp before importing the lab")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
CTX_CODE = os.path.join(LAB, "r2", "tracks", "autopsy", "context")
for p in (LAB, os.path.join(LAB, "r2"), CTX_CODE, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

# the context lens's verified helpers (imported, never modified): registry of the ten sleeves, in-sample loaders,
# simulation wrapper, descriptor code. Their module is named `common`; ours are prefixed cv_ to avoid the clash.
import common as CC  # noqa: E402
import descr as D  # noqa: E402

OUT = os.path.join(LAB, "results", "r2", "sizing", "conviction")
os.makedirs(OUT, exist_ok=True)
CTX_OUT = os.path.join(LAB, "results", "r2", "autopsy", "context")
SIG_DIR = os.path.join(CTX_OUT, "signals")
CH_DIR = os.path.join(CTX_OUT, "chains")
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
IS_END_NS = int(IS_END.value)
NS_DAY = 86_400 * 10 ** 9
PURGE_NS = 7 * NS_DAY
MODES = ("fp", "stress")
OOF_YEARS = (2019, 2020, 2021)

KEYS = list(CC.KEYS)                      # the ten sleeves, "<name>__<sym>"
SYM = {k: k.split("__")[1] for k in KEYS}
MARKETS = ("us100", "xauusd", "btcusd", "ethusd")
CRYPTO_BRK = ("brk72_24h_wd__btcusd", "brk72_24h_wd__ethusd", "F1_brk_ridge_filter__btcusd",
              "F1_brk_ridge_filter__ethusd")

# descriptors eligible for the conviction stakes (declared.json): the context lens's causal descriptors, minus the
# clock (hour, weekday: lens `clock`), minus sprR (the FP frames' spread is scaled by the day's median spread, which is
# not causal -- brain map `simulateur`), replaced by riskbp = 10,000 x risk / P (the rule's own stop distance in basis
# points of the last mid close before the decision; context lens respec.py).
ELIGIBLE = ["vol", "al1", "al5", "al20", "room", "cushion", "trig", "riskbp", "rel", "rel2", "prev", "oth24"]
PART1_EXTRA = ["hour_dec", "dow", "sprR"]          # reported in part 1 only (not used by any stake)


def year_start_ns(y):
    return int(pd.Timestamp(f"{y}-01-01", tz="UTC").value)


def train_cut_ns(y):
    """a training trade for year y must have its outcome known by 1 January y minus 7 days (exit_time <= this)"""
    return year_start_ns(y) - PURGE_NS


def ns(ts):
    return D.ns_of(ts)


# ------------------------------------------------------------------------------------------- server clock / weeks
def server_days(t_ns):
    """int64 ns UTC -> FP server calendar day number (days since 1970-01-01, server = New York + 7 h)"""
    loc = pd.DatetimeIndex(np.asarray(t_ns, np.int64).astype("datetime64[ns]")).tz_localize("UTC") \
        .tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    return (loc.values.astype("datetime64[D]") - np.datetime64("1970-01-01", "D")).astype(np.int64)


def server_week(t_ns):
    """Monday-based server week number (day 0 = Thursday 1970-01-01, so (day + 3) // 7 starts weeks on Monday)"""
    return (server_days(t_ns) + 3) // 7


def week_thursday_year(w):
    d = np.datetime64("1970-01-01", "D") + (7 * np.asarray(w, np.int64)).astype("timedelta64[D]")
    return pd.DatetimeIndex(d).year.to_numpy()


def week_monday(w):
    return np.datetime64("1970-01-01", "D") + (7 * np.asarray(w, np.int64) - 3).astype("timedelta64[D]")


def oof_weeks(years=OOF_YEARS):
    """server weeks whose Thursday falls in `years` (contiguous range)"""
    lo = int((np.datetime64(f"{min(years)}-01-01", "D") - np.datetime64("1970-01-01", "D")).astype(np.int64))
    hi = int((np.datetime64(f"{max(years)}-12-31", "D") - np.datetime64("1970-01-01", "D")).astype(np.int64))
    # Thursday of week w is day 7w
    w0 = -(-lo // 7)
    w1 = hi // 7
    w = np.arange(w0, w1 + 1)
    assert set(week_thursday_year(w)) == set(years)
    return w


# ------------------------------------------------------------------------------------------- loading
def load_signals(k, mode):
    s = pd.read_parquet(os.path.join(SIG_DIR, f"{k}__{mode}.parquet"))
    assert int(s.t_dec.max()) < IS_END_NS
    s = s.copy()
    s["riskbp"] = s.risk / s.P * 1e4
    hr, dw = D.clock(s.t_dec.to_numpy(np.int64))
    s["hour_dec"] = hr
    assert (dw == s.dow.to_numpy()).all()
    return s


def load_chain(k, mode):
    c = pd.read_parquet(os.path.join(CH_DIR, f"{k}__{mode}.parquet"))
    assert (c.entry_time < IS_END).all() and (c.exit_time < IS_END).all()
    return c.sort_values("entry_time", kind="stable").reset_index(drop=True)


def load_official_is(name, sym):
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"), filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------- agreement
def agreement(t_dec, side, others):
    """n_same, n_opp at each decision time: number of OTHER sleeves of the same market whose (realised) chain holds a
    position at t_dec, same side / opposite side. A position is held at t if entry_time < t < exit_time (the fill bar
    started before t, so the fill is done by t; exit_time is the exit bar start for time exits and start + 1 min
    otherwise, so exit_time > t means the exit has not happened by t). `others`: list of DataFrames with entry_ns,
    exit_ns, side."""
    t_dec = np.asarray(t_dec, np.int64)
    side = np.asarray(side, np.int64)
    n_same = np.zeros(len(t_dec), np.int64)
    n_opp = np.zeros(len(t_dec), np.int64)
    for o in others:
        if len(o) == 0:
            continue
        e = o["entry_ns"].to_numpy(np.int64)
        x = o["exit_ns"].to_numpy(np.int64)
        sd = o["side"].to_numpy(np.int64)
        order = np.argsort(e, kind="stable")
        e, x, sd = e[order], x[order], sd[order]
        # one-position chains: at most one open trade per other sleeve at any time -> the last entry before t
        j = np.searchsorted(e, t_dec, side="left") - 1
        ok = j >= 0
        jj = np.maximum(j, 0)
        held = ok & (x[jj] > t_dec)
        n_same += (held & (sd[jj] == side)).astype(np.int64)
        n_opp += (held & (sd[jj] != side)).astype(np.int64)
    return n_same, n_opp


def chain_frame(c):
    """minimal view of a chain for the agreement descriptor"""
    return pd.DataFrame({"entry_ns": ns(c.entry_time), "exit_ns": ns(c.exit_time), "side": c.side.to_numpy(np.int64),
                         "oid": c.oid.to_numpy(np.int64)})


# ------------------------------------------------------------------------------------------- portfolio measures
def longest_neg_run(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return int(best)


def weekly(book, weeks):
    """book: DataFrame with columns week, pnl (stake x R). Returns the weekly sums over `weeks` (zeros included)."""
    s = book.groupby("week")["pnl"].sum()
    return s.reindex(weeks, fill_value=0.0).to_numpy(np.float64)


def sharpe(w):
    sd = float(np.std(w, ddof=1))
    return float(np.mean(w) / sd * np.sqrt(52)) if sd > 0 else float("nan")


def measures(book, weeks, scale=1.0, months=None):
    """portfolio measures on the weeks `weeks` (stake x R already in book.pnl; `scale` multiplies every stake)"""
    w = weekly(book, weeks) * scale
    inw = book.week.isin(weeks).to_numpy()
    b = book[inw]
    taken = b.stake.to_numpy() > 0
    los = taken & (b.R.to_numpy() < 0)
    n_m = months if months is not None else len(weeks) * 12 / 52.18
    return {"weeks": int(len(w)), "sharpe": round(sharpe(w), 4), "mean_w": round(float(w.mean()), 4),
            "sd_w": round(float(np.std(w, ddof=1)), 4), "total_R": round(float(w.sum()), 2),
            "losing_weeks_pct": round(float(100 * (w < 0).mean()), 2), "worst_week": round(float(w.min()), 2),
            "longest_losing_weeks": longest_neg_run(w), "trades": int(taken.sum()),
            "losing_trades_per_month": round(float(los.sum() / n_m), 2),
            "mean_stake": round(float(b.stake.to_numpy()[taken].mean()) * scale, 4) if taken.any() else None}


def dump(obj, path):
    def conv(o):
        if hasattr(o, "item"):
            return o.item()
        if isinstance(o, (set, tuple)):
            return list(o)
        return str(o)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=conv)


def append_jsonl(path, row):
    def conv(o):
        if hasattr(o, "item"):
            return o.item()
        return str(o)
    with open(path, "a") as f:
        f.write(json.dumps(row, default=conv) + "\n")
