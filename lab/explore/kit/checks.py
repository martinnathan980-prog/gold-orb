"""Guards a run calls before trusting a pass."""
import hashlib
import os

import numpy as np
import pandas as pd

from . import data as _data
from . import sim
from . import stats as S

_PRICE_COLS = ("open", "high", "low", "close")


_SCALE_FREE = ("volume", "n_bars")       # columns of data.load_bars / daily_bars that are not prices
_PER_SHARE = ("shares",)                 # kit v2.2: a share count (Yahoo's traded volume, split-adjusted like the prices):
                                         # re-based by the INVERSE factor, so price x shares (dollar volume) is unchanged
ROW_LEN_COLUMN = "known_at"              # kit v2.2: row_len='known_at' = each row is complete at its own known_at


def _adj_key(k):
    if not isinstance(k, str):
        return False
    try:
        return bool(_data.has_adjustment(k))
    except KeyError:
        return False


def _adj_name(k):
    """An adjusted market recognised by a column or Series NAME: the oil and the 40 shares only. Kit v2.2: the keys of
    the daily universe are tickers ('low', 'key', 'a', 'all', 'now', ...) that are also ordinary column names, so they
    are recognised by attrs 'market' (data.load_bars) or by the rows of a long frame's 'market' column, never by a name."""
    return _adj_key(k) and _data._C.market_class(k) is None


_SESSION_CLOCKS = (570, 780, 960)        # kit v2.2 fix (V22-3/V22-5): 09:30 (a session's open), 13:00 and 16:00 New
                                         # York (its close): the only clock times of the daily shares' own stamps


def _ny_minutes(idx):
    ny = pd.DatetimeIndex(idx).tz_convert("America/New_York")
    return ny.hour.to_numpy() * 60 + ny.minute.to_numpy()


def _session_stamped(x):
    """True if x has a tz-aware DatetimeIndex whose every time is a session's open or close (09:30, 13:00, 16:00 New
    York) and at least one is an open or a close: the index of daily share values (data.load_bars and its derivations, or
    the same values re-indexed to their known_at)."""
    idx = x.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None or not len(idx):
        return False
    return bool(np.isin(_ny_minutes(idx), _SESSION_CLOCKS).all())


def _class_keys_of(x):
    """Kit v2.2 fix (V22-3/V22-5): the class shares an input WITHOUT attrs 'market' carries by name: a wide frame whose
    columns are ALL keys of kit/universe_us.csv (closes of several shares side by side), or a Series named after one,
    with a session-stamped index (_session_stamped). Tickers that are also ordinary names ('low', 'key', 'a') are then
    recognised only with these two marks together, never by a column name alone."""
    at = getattr(x, "attrs", {}) or {}
    if at.get("market") is not None or not _session_stamped(x):
        return []
    if isinstance(x, pd.Series):
        return [x.name] if _data._C.market_class(x.name) is not None else []
    if isinstance(x, pd.DataFrame) and len(x.columns) and "market" not in x.columns and \
            all(_data._C.market_class(c) is not None for c in x.columns):
        return list(x.columns)
    return []


def _ref_range(key, x, refs):
    """(low, high) of the market's adjusted prices: attrs['price_range'] (data.load_bars sets it; pandas keeps it on
    derived frames), else the item's own low / high columns, else the bars data.load_bars(key) gives."""
    at = getattr(x, "attrs", {})
    if at.get("market") == key and at.get("price_range"):
        return tuple(at["price_range"])
    if isinstance(at.get("price_ranges"), dict) and key in at["price_ranges"]:     # kit v2.2: data.long_bars
        return tuple(at["price_ranges"][key])
    if isinstance(x, pd.DataFrame) and at.get("market") == key and {"low", "high"} <= set(x.columns) and len(x):
        return float(x["low"].min()), float(x["high"].max())
    if key not in refs:
        try:
            b = _data.load_bars(key)
            refs[key] = (float(b.low.min()), float(b.high.max()))
        except Exception as e:      # noqa: BLE001
            refs[key] = e
    if isinstance(refs[key], Exception):
        raise ValueError(f"truncation_test: an input carries the adjusted market '{key}' but its price level cannot be "
                         f"checked ({refs[key]!r}): pass the bars of data.load_bars and compute features inside build")
    return refs[key]


def _price_like(v, rng):
    """True if >= 99 % of the finite values lie within [0.5 x low, 2 x high] of the market's adjusted prices."""
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return True
    lo, hi = rng
    return bool(np.mean((v >= 0.5 * lo) & (v <= 2.0 * hi)) >= 0.99)


def _refuse(label, col, key):
    raise ValueError(
        f"truncation_test: input {label!r}{'' if col is None else f' column {col!r}'} carries the back-adjusted market "
        f"'{key}' but is not at its price level (a return, a difference, a z-score...): it cannot be re-based to the "
        "adjustment known at each cut (a price difference must be, a return must not), so the test could fail an honest "
        "rule or pass a rule on adjusted levels. Compute features INSIDE build from the bars of data.load_bars passed in "
        "`data` (kit v2.1 fix 3, R3-2/R3-3)")


def _plan_item(x, label, refs):
    """Kit v2.1 fix 3 (R3-2/R3-3): which values of one input of a truncation test are adjusted prices to re-base at each
    cut: [(column or None for a Series, market key, row mask or None)]. Recognised: (a) a frame or Series whose attrs
    'market' is a back-adjusted market (data.load_bars bars, data.daily_bars, a slice, a renamed close...): every float
    column (but volume / n_bars) must be at the market's price level (re-based) or the input is REFUSED (ValueError);
    (b) a frame without such attrs: columns named after an adjusted market (a wide frame of several shares' closes) and,
    in a long frame with a 'market' column, the open / high / low / close of the rows of an adjusted market; each must be
    at that market's price level or the input is refused; (c) a Series named after an adjusted market."""
    plan = []
    at = getattr(x, "attrs", {}) or {}
    key = at.get("market")
    if isinstance(x, pd.Series):
        k = key if _adj_key(key) else (x.name if _adj_name(x.name) else None)
        if k is None and _class_keys_of(x):                   # kit v2.2 fix (V22-5): a Series named after a share
            k = x.name
        if k is None or not pd.api.types.is_float_dtype(x.dtype):
            return plan
        if not _price_like(x.to_numpy(), _ref_range(k, x, refs)):
            _refuse(label, None, k)
        return [(None, k, None)]
    if not isinstance(x, pd.DataFrame):
        return plan
    if _adj_key(key):
        rng = _ref_range(key, x, refs)
        for col in x.columns:
            if col in _PER_SHARE and _data._C.market_class(key) is not None and \
                    pd.api.types.is_float_dtype(x[col].dtype):
                plan.append((col, key, None, -1))            # kit v2.2: a share count, re-based by 1 / the factor
                continue
            if col in _SCALE_FREE or not pd.api.types.is_float_dtype(x[col].dtype):
                continue
            if not _price_like(x[col].to_numpy(), rng):
                _refuse(label, col, key)
            plan.append((col, key, None))
        return plan
    wide = set(_class_keys_of(x))                            # kit v2.2 fix (V22-5): a wide frame of class shares
    for col in x.columns:
        if (_adj_name(col) or col in wide) and pd.api.types.is_float_dtype(x[col].dtype):
            if not _price_like(x[col].to_numpy(), _ref_range(col, x, refs)):
                _refuse(label, col, col)
            plan.append((col, col, None))
    if "market" in x.columns:
        # kit v2.2 fix (V22-10): ONE integer code per row (the position of its market among the adjusted markets, -1 for
        # the others) instead of a boolean row mask per market and column: 382 shares x 5 columns of masks were ~1 GB
        codes, uniq = pd.factorize(x["market"].to_numpy())
        adj = [i for i, k in enumerate(uniq) if _adj_key(k)]
        if adj:
            remap = np.full(len(uniq) + 1, -1, np.int32)
            remap[adj] = np.arange(len(adj), dtype=np.int32)
            rc = remap[codes]                                # factorize gives -1 for a missing market: remap[-1] = -1
            keys = tuple(str(uniq[i]) for i in adj)
            for col in _PRICE_COLS:
                if col in x.columns and pd.api.types.is_float_dtype(x[col].dtype):
                    v = x[col].to_numpy()
                    for j, k in enumerate(keys):
                        if not _price_like(v[rc == j], _ref_range(k, x, refs)):
                            _refuse(label, col, k)
                    plan.append((col, None, {"codes": rc, "keys": keys, "pow": np.ones(len(keys))}))
            for col in _PER_SHARE:                           # kit v2.2: share counts of a daily share's rows (1 / q)
                if col in x.columns and pd.api.types.is_float_dtype(x[col].dtype):
                    pw = np.array([-1.0 if _data._C.market_class(k) is not None else 0.0 for k in keys])
                    if (pw != 0).any():
                        plan.append((col, None, {"codes": rc, "keys": keys, "pow": pw}))
    return plan


def _plan_keys(plan):
    """The market keys a plan re-bases (kit v2.2 fix V22-10: a long frame's item names its keys in item[2]['keys'])."""
    out = set()
    for p in plan:
        if isinstance(p[2], dict):
            out.update(p[2]["keys"])
        else:
            out.add(p[1])
    return out


def _scale_plan(data):
    """{item name: plan} for a dict of inputs, or {None: plan} for a single input (see _plan_item)."""
    refs = {}
    if isinstance(data, dict):
        return {k: _plan_item(v, k, refs) for k, v in data.items()}
    return {None: _plan_item(data, "data", refs)}


def _asof_prices(x, c, plan):
    """Kit v2.1 fix 2/3 (KF-2, R3-1): the cut copy x of an input re-based to the adjustment known at the cut c: the
    adjusted prices named by `plan` are multiplied by data._asof_q(market) inside asof(c), an exact power of two (so
    sums, differences, ratios and comparisons stay bit-identical while absolute levels move); attrs 'splits_applied'
    keeps the splits before c only. The plan's row masks are those of x's rows."""
    if not plan or not len(x):
        return x
    with _data.asof(c):
        qs = {k: _data._asof_q(k) for k in _plan_keys(plan)}
    if all(q == 1.0 for q in qs.values()):
        return x
    if isinstance(x, pd.Series):
        out = x * qs[plan[0][1]]
    else:
        out = x.copy()
        for item in plan:
            col, k, m = item[:3]
            if isinstance(m, dict):                          # kit v2.2 fix (V22-10): a long frame, one code per row
                qv = np.r_[[qs[kk] ** p for kk, p in zip(m["keys"], m["pow"])], 1.0]
                if (qv == 1.0).all():
                    continue
                out[col] = out[col].to_numpy(float) * qv[m["codes"]]     # code -1 -> the last factor, 1.0
                continue
            if qs[k] == 1.0:
                continue
            f = qs[k] if len(item) < 4 else qs[k] ** item[3]         # kit v2.2: share counts by 1 / the factor
            v = out[col].to_numpy(float).copy()
            if m is None:
                v = v * f
            else:
                v[m] = v[m] * f
            out[col] = v
    out.attrs.update(x.attrs)
    k0 = (x.attrs or {}).get("market")
    if k0 in qs and out.attrs.get("price_range"):
        out.attrs["price_range"] = tuple(float(v) * qs[k0] for v in x.attrs["price_range"])
    if "splits_applied" in out.attrs:
        cc = pd.Timestamp(c)
        out.attrs["splits_applied"] = {d: q for d, q in x.attrs["splits_applied"].items()
                                       if pd.Timestamp(d).tz_localize("America/New_York") < cc}
    return out


def _cut(data, c, lens, plan=None):
    if isinstance(data, dict):
        if isinstance(lens, dict):
            miss = [k for k in data if k not in lens]
            if miss:
                raise ValueError(f"truncation_test: no row_len for {miss}: give each item's row length (1 h for hourly "
                                 "bars indexed by their open, 0 for a series indexed by the time its value is KNOWN)")
            return {k: _cut1(v, c, lens[k], (plan or {}).get(k)) for k, v in data.items()}
        return {k: _cut1(v, c, lens, (plan or {}).get(k)) for k, v in data.items()}
    return _cut1(data, c, lens, (plan or {}).get(None))


def _row_ends(x, lens):
    """int64 ns completion time of each row of x: index + lens, or (lens = 'known_at', kit v2.2) the row's own known_at
    column (daily session bars of data.load_bars: the session's close, 16:00 or 13:00 New York)."""
    if isinstance(lens, str):
        if lens != ROW_LEN_COLUMN or not isinstance(x, pd.DataFrame) or lens not in x.columns:
            raise ValueError(f"truncation_test: row_len '{lens}' names a column of the item (only '{ROW_LEN_COLUMN}', the "
                             "time each row is complete, as data.load_bars gives daily session bars)")
        e = pd.DatetimeIndex(x[lens])
        e = e.tz_localize("UTC") if e.tz is None else e.tz_convert("UTC")
        ix = pd.DatetimeIndex(x.index)
        ix = ix.tz_localize("UTC") if ix.tz is None else ix.tz_convert("UTC")
        if (e < ix).any():
            raise ValueError("truncation_test: a row's known_at is before its index time")
        return e.as_unit("ns").asi8
    idx = pd.DatetimeIndex(x.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    return (idx + pd.Timedelta(lens)).as_unit("ns").asi8


def _check_row_len(x, lens, label):
    """Kit v2.2: an item of daily session bars must be cut at each row's own close: row_len='known_at', or a Timedelta
    at least as long as its longest session (6.5 h). A shorter one (1 h, 0) would let a cut keep a session whose close is
    not known yet: the test would be blind to a build that reads the day's close before 16:00.
    Daily items (kit v2.2 fix V22-3): attrs bar 'session' or a market of a cost class (data.load_bars, its slices, a
    close Series taken from it, a frame with known_at dropped), a long frame with a 'market' column of class shares, a
    wide frame or Series named after class shares (_class_keys_of) whose index holds a session's OPEN (09:30 New York).
    Such an input without a known_at column counts a full session (6.5 h); re-indexed to the closes (13:00 / 16:00:
    each value at the time it is known) it may take row_len 0."""
    if isinstance(lens, str) or not isinstance(x, (pd.DataFrame, pd.Series)) or not len(x):
        return
    at = getattr(x, "attrs", {}) or {}
    mk = x["market"].astype(str).to_numpy() if isinstance(x, pd.DataFrame) and "market" in x.columns else None
    named = _class_keys_of(x)
    daily = at.get("bar") == "session" or _data._C.market_class(at.get("market")) is not None or bool(named) or (
        mk is not None and any(_data._C.market_class(k) is not None for k in pd.unique(mk)))
    if not daily:
        return
    if isinstance(x, pd.DataFrame) and ROW_LEN_COLUMN in x.columns:
        e = pd.DatetimeIndex(x[ROW_LEN_COLUMN])
        e = e.tz_localize("UTC") if e.tz is None else e.tz_convert("UTC")
        ix = pd.DatetimeIndex(x.index)
        ix = ix.tz_localize("UTC") if ix.tz is None else ix.tz_convert("UTC")
        longest = (e - ix).max()
        fix = f"Pass row_len='{ROW_LEN_COLUMN}' (each bar complete at its own close) for this item"
    else:
        ix = pd.DatetimeIndex(x.index)
        if _session_stamped(x) and not (_ny_minutes(ix) == 570).any():
            return                                        # values re-indexed to the sessions' closes: row_len 0 is right
        longest = pd.Timedelta(minutes=max(_data.SESSION_MINUTES))
        fix = ("It has no known_at column: give it row_len >= 6.5 h, or re-index its values to the time they are "
               "known (the bars' known_at) and give row_len 0, or pass the bars of data.load_bars with "
               f"row_len='{ROW_LEN_COLUMN}'")
    if pd.Timedelta(lens) < longest:
        raise ValueError(f"truncation_test: item {label!r} holds daily session bars (open 09:30, close known at 16:00 or "
                         f"13:00 New York) but its row_len is {pd.Timedelta(lens)}, shorter than its longest session "
                         f"({longest}): a cut would keep a session before its close is known. {fix} (kit v2.2 fix V22-3)")


def _cut1(x, c, lens, plan):
    keep = _row_ends(x, lens) <= pd.Timestamp(c).as_unit("ns").value
    if plan:
        plan = [(item[0], item[1], None if item[2] is None else
                 (dict(item[2], codes=item[2]["codes"][keep]) if isinstance(item[2], dict) else item[2][keep]))
                + tuple(item[3:]) for item in plan]
    return _asof_prices(x[keep], c, plan)


# Minimum cut density judge.verdict requires of a truncation report (verifier V1, 2026-11-18: a build that DROPS an
# event or signal when the future is favourable, written so that a NaN at the end of a cut keeps it, is seen only by a
# cut a few bars after a dropped row; 8 cuts at kept rows' stamps caught it in 1 seed of 10, 50 stamp cuts or 100 random
# bar-end cuts in 10 of 10).
MIN_STAMP_CUTS = 50
MIN_AFTER_CUTS = 50
MIN_RANDOM_CUTS = 100
AFTER_BARS = 24


def _bar_ends(data, lens):
    """Sorted unique int64 ns of every row's completion time (index + row_len) over all items of data."""
    if isinstance(data, dict):
        if isinstance(lens, dict):
            miss = [k for k in data if k not in lens]
            if miss:
                raise ValueError(f"truncation_test: no row_len for {miss}: give each item's row length (1 h for hourly "
                                 "bars indexed by their open, 0 for a series indexed by the time its value is KNOWN)")
            parts = [_bar_ends(v, lens[k]) for k, v in data.items()]
        else:
            parts = [_bar_ends(v, lens) for v in data.values()]
        return np.unique(np.concatenate(parts)) if parts else np.array([], np.int64)
    return np.unique(_row_ends(data, lens))


def cuts_ok(rep):
    """(ok, why): does a truncation report carry the cut density judge.verdict requires? At least
    min(MIN_STAMP_CUTS, n_signals) cuts at rows' own time stamps, as many cuts 1-AFTER_BARS bar ends after them, and
    min(MIN_RANDOM_CUTS, bar ends available) random bar-end cuts across the history."""
    n = int(rep.get("n_signals", 0))
    need_s = min(MIN_STAMP_CUTS, n)
    if rep.get("n_signal_cuts", 0) < max(1, need_s) and n > 0:
        return False, f"too few cuts at a row's own time stamp ({rep.get('n_signal_cuts', 0)} < {max(1, need_s)})"
    if rep.get("n_after_tried", 0) < min(MIN_AFTER_CUTS, n):
        return False, f"too few cuts just after the rows' stamps ({rep.get('n_after_tried', 0)} < {min(MIN_AFTER_CUTS, n)})"
    need_r = min(MIN_RANDOM_CUTS, int(rep.get("n_bar_ends", 0)))
    if "n_random_cuts" not in rep or rep["n_random_cuts"] < need_r:
        return False, f"too few random bar-end cuts ({rep.get('n_random_cuts', 0)} < {need_r})"
    return True, "enough cuts"


def truncation_test(build, data, cuts=(), row_len=pd.Timedelta(hours=1), cols=("known_at", "side"),
                    n_signal_cuts=MIN_STAMP_CUTS, seed=0, n_random_cuts=MIN_RANDOM_CUTS, n_after_cuts=None):
    """Rebuild the signal table on data cut at each date and compare with the full build: the signals known at or before
    the cut must be identical (same rows, same `cols`, plus 'market' if present). `data`: a frame or a dict of frames /
    series indexed by UTC time; `row_len`: how long after its index time a row is complete (1 h for hourly bars indexed
    by their open; 0 for a series indexed by the time its value is KNOWN; 'known_at' for daily session bars, kit v2.2); a dict gives one per item and must name every item (a missing one raises: a
    default of 0 would make the test blind to a bar's own close). A cut at c keeps
    the rows complete by c (index + row_len <= c). So a signal stamped known_at = t that secretly uses a bar ending
    after t, or a value known after t, changes or vanishes in the cut build and the test fails (lab round 6
    truncation.py, at signal level). `build(data)` returns a signal table with known_at.
    Cuts, besides the given `cuts` (verifier V1: dense by default):
      - n_signal_cuts (50) cuts exactly at the known_at of signals drawn from the full build (the sharpest cut for a
        signal that uses data after its own stamp: it vanishes or changes);
      - n_after_cuts (default = as many) cuts 1-24 bar ends after drawn signals' stamps, and n_random_cuts (100) cuts at
        random bar ends (index + row_len of the data) across the history: they catch a build that DROPS a row when the
        future is favourable (a row kept only because the future is NaN at the end of a cut reappears in the cut build;
        no cut at a kept row's own stamp lands on a dropped one).
    The report carries the counts; judge.verdict requires checks.cuts_ok (>= min(50, n) stamp cuts, >= min(50, n)
    after-cuts, >= min(100, bar ends) random cuts). A row dropped only by a look-ahead of h bars is seen by a cut in the
    h bar ends after it: the test is sampled, so a very rare dropped row can still slip through (README 'limits').
    The report carries `signals_sha` (sim.signals_sha of the full build): judge.verdict requires a passing report whose
    signals_sha equals the main configuration's simulated signals (trades.attrs['signals_sha']). So build the WHOLE
    signal table inside `build` (filters included) and simulate exactly build(data) (adding a 'market' column is fine).
    EVENT builds (exit on a condition): a build returning a table WITHOUT 'side' (columns known_at = when the exit
    condition is known to be true, optional market) is tested the same way; the report then carries `events_sha`
    (sim.events_sha of the full build, signals_sha None) and `events_by_key` (sha per market key, '*' for a table without
    market), and judge.verdict binds it to the events each simulated market used (pass it as event_truncation=).
    BACK-ADJUSTED BARS (kit v2.1 fix 2, KF-2; fix 3, R3-1..R3-3): share bars with splits and oil bars with rolls carry,
    before a roll or a split, the factor of every later one. Each cut build runs inside data.asof(cut), and each cut copy
    of such bars is re-based: multiplied by data._asof_q, an EXACT POWER OF TWO standing for the adjustment known at the
    cut (2 ** round(log2 k), 2 or 1/2 when that rounds to 1); data.load_bars, price_factor and split_factor inside the
    cut build give the same re-basing. Sums, differences, ratios and comparisons of prices are then bit-identical in the
    full and the cut build (an honest rule cannot flip on a floating-point tie), while any absolute adjusted level
    differs, so a rule on levels (or on price_factor) fails. Which inputs are re-based (_plan_item): any frame or Series
    whose attrs 'market' names an adjusted market (data.load_bars, data.daily_bars, slices, a renamed close), whatever
    the column or Series name; columns named after an adjusted market in a frame without attrs (a wide frame of closes);
    open/high/low/close of an adjusted market's rows in a long frame with a 'market' column. Each such float column must
    be at the market's price level (attrs 'price_range'), else the test REFUSES the input (ValueError): a return, a
    price difference or a z-score cannot be re-based correctly, so compute features INSIDE build. A derived input that
    carries none of these marks (a numpy array, a new unnamed Series of another name, a frame built from it) is not seen:
    build signals from the bars passed in `data` (README 'limits').
    DAILY SHARES (kit v2.2, data.load_bars of a key of kit/universe_us.csv): give their item row_len='known_at' (each
    session bar is complete at its own close: 16:00, or 13:00 on a half day); a Timedelta shorter than the longest
    session (6.5 h) is refused, since a cut would then keep a session whose close is not known yet; so is a row_len
    under 6.5 h for a daily input WITHOUT known_at (a close Series, a wide frame of closes named by ticker: kit v2.2 fix
    V22-3; re-indexed to the closes, such an input may take 0). Their levels carry splits after 2021 that no list holds,
    so every cut copy is re-based by the share's own power of two, 2 to 2,048 (data.class_q, fix V22-5), and their
    'shares' column by its inverse: a rule on a price level, on levels compared across shares or on a raw share count
    fails, a rule on ratios (or on price x shares) is bit-identical. A long frame of several shares (data.long_bars, a
    'market' column) works the same way (one integer code per row, fix V22-10), and so does a wide frame or a Series
    named after shares of the universe with a session-stamped index.
    `cols`: compare only known_at, side and integer or label columns: a float feature (a log return, a z-score) differs
    in its last bits under the re-basing (log(2 x) - log(2 y) is not bit-identical to log x - log y) and fails an honest
    rule; compute it inside build and keep it out of cols."""
    plan = _scale_plan(data)                              # kit v2.1 fix 3: refuses unclassifiable adjusted inputs
    for k_, v_ in (data.items() if isinstance(data, dict) else [(None, data)]):    # kit v2.2: daily bars' row_len
        if isinstance(row_len, dict) and k_ not in row_len:
            continue                                      # (a missing row_len raises below, as before)
        _check_row_len(v_, row_len[k_] if isinstance(row_len, dict) else row_len, k_ or "data")
    full = build(data)
    ends = _bar_ends(data, row_len)                       # also refuses a dict without a row_len for every item
    is_ev = "side" not in full
    rep = {"cuts": [], "pass": True, "signals_sha": None if is_ev else sim.signals_sha(full), "n_signals": int(len(full)),
           "n_signal_cuts": 0, "n_after_cuts": 0, "n_after_tried": 0, "n_random_cuts": 0}
    if is_ev:
        rep["events_sha"] = sim.events_sha(full)
        rep["events_by_key"] = sim.events_by_key(full)
    rng = np.random.default_rng(seed)
    cuts = [pd.Timestamp(c) for c in cuts]
    if n_signal_cuts and len(full):
        ka = pd.DatetimeIndex(full.known_at)
        pick = rng.choice(len(ka), min(n_signal_cuts, len(ka)), replace=False)
        stamps = ka[np.sort(pick)]
        cuts += list(stamps)
        rep["n_signal_cuts"] = int(len(pick))
        na = len(pick) if n_after_cuts is None else min(int(n_after_cuts), len(pick))
        if na and len(ends):
            sa = (stamps.tz_convert("UTC") if stamps.tz is not None else stamps.tz_localize("UTC")).as_unit("ns").asi8
            sel = np.sort(rng.choice(len(sa), na, replace=False))
            pos = np.searchsorted(ends, sa[sel], side="right") + rng.integers(0, AFTER_BARS, na)
            okp = pos < len(ends)
            cuts += list(pd.DatetimeIndex(ends[pos[okp]].astype("datetime64[ns]")).tz_localize("UTC"))
            rep["n_after_cuts"] = int(okp.sum())          # a stamp at the very end of the data has no bar end after it
            rep["n_after_tried"] = int(na)
    if n_random_cuts and len(ends) > 1:
        pool = ends[:-1]                                  # a cut at the last bar end is the full build
        if len(full):
            ka = pd.DatetimeIndex(full.known_at)
            ka = (ka.tz_convert("UTC") if ka.tz is not None else ka.tz_localize("UTC")).as_unit("ns").asi8
            lo, hi = ka.min() - 7 * 86400 * 10 ** 9, ka.max() + 7 * 86400 * 10 ** 9
            pool = pool[(pool >= lo) & (pool <= hi)] if ((pool >= lo) & (pool <= hi)).any() else pool
        rep["n_bar_ends"] = int(len(pool))
        pr = np.sort(rng.choice(len(pool), min(n_random_cuts, len(pool)), replace=False))
        cuts += list(pd.DatetimeIndex(pool[pr].astype("datetime64[ns]")).tz_localize("UTC"))
        rep["n_random_cuts"] = int(len(pr))
    else:
        rep["n_bar_ends"] = int(max(len(ends) - 1, 0))
    keep = [c for c in (["market"] if "market" in full else []) + list(cols) if c in full]
    fka = pd.DatetimeIndex(full.known_at)
    for c in cuts:
        c = c.tz_localize("UTC") if c.tz is None else c
        cd = _cut(data, c, row_len, plan)                 # re-based to the rolls / splits known at the cut (KF-2, R3-1)
        with _data.asof(c):                               # and the build sees them as known at the cut
            part = build(cd)
        a = full[fka <= c][keep].reset_index(drop=True)
        b = part[pd.DatetimeIndex(part.known_at) <= c][keep].reset_index(drop=True)
        same = len(a) == len(b) and all((a[k].to_numpy() == b[k].to_numpy()).all() for k in keep)
        rep["cuts"].append({"cut": str(c), "n_full": int(len(a)), "n_cut": int(len(b)), "equal": bool(same)})
        rep["pass"] &= bool(same)
    rep["n_failed_cuts"] = int(sum(not x["equal"] for x in rep["cuts"]))
    rep["density_ok"], rep["density_why"] = cuts_ok(rep)
    return rep


SESSION_SHIFT_MIN_H = 17.5      # kit v2.2 fix (V22-6): a close (16:00) to the next session's open (09:30)
SESSION_SHIFT_DEFAULT_H = 24.0


def _is_session_key(k):
    try:
        return bool(k) and _data._C.bar_kind(k) == "session"
    except Exception:      # noqa: BLE001 (a key without a cost entry)
        return False


def _book_keys(bars):
    if isinstance(bars, dict):
        return [str(k) for k in bars]
    return [str(getattr(bars, "key", ""))]


def shift_test(signals, bars, delay_extra_h=None, max_wait_h=None, **rule):
    """The same signals entered one bar (delay_extra_h hours) later: reported, not judged. A rule whose result
    collapses with a one-hour delay lives on the entry bar itself: look for look-ahead or a fragile clock.
    max_wait_h is passed to BOTH simulations (counted from each run's own known_at + delay_h: a signal whose entry bar
    opens more than max_wait_h after that is dropped as stale), so the shifted run keeps the main's staleness rule; the
    report carries each run's stale count.
    delay_extra_h: one bar. None (the default) = 1 h, or 24 h when a market of `bars` has one bar a session (kit v2.2
    daily shares): one hour moves no daily entry, so a shift of less than 17.5 h (a close to the next open) is REFUSED
    there (kit v2.2 fix V22-6)."""
    sess = [k for k in _book_keys(bars) if _is_session_key(k)]
    if delay_extra_h is None:
        delay_extra_h = SESSION_SHIFT_DEFAULT_H if sess else 1.0
    elif sess and float(delay_extra_h) < SESSION_SHIFT_MIN_H:
        raise ValueError(f"shift_test: {len(sess)} market(s) of one bar a session ({sess[:3]}...): a shift of "
                         f"{delay_extra_h} h moves no entry (the next bar opens 17.5 h or more after a close). Give "
                         f"delay_extra_h >= {SESSION_SHIFT_MIN_H} (default {SESSION_SHIFT_DEFAULT_H}: one session)")
    d0 = float(rule.pop("delay_h", 0.0))
    a = sim.simulate(signals, bars, delay_h=d0, max_wait_h=max_wait_h, **rule)
    b = sim.simulate(signals, bars, delay_h=d0 + delay_extra_h, max_wait_h=max_wait_h, **rule)
    f = lambda t: {"n": int(len(t)), "PF": S.pf(t.R), "mean_R": float(t.R.mean()) if len(t) else None,  # noqa: E731
                   "PF_gross": S.pf(t.R_gross), "stale": int(sum(c.get("stale", 0) for c in t.attrs["counts"].values()))}
    return {"base": f(a), "shifted": f(b), "delay_extra_h": delay_extra_h, "max_wait_h": max_wait_h}


def min_commission_test(signals, bars, max_wait_h=None, **rule):
    """Kit v2.2 fix (V22-2): a SENSITIVITY, reported, not judged. The daily shares pay max(0.03 USD a share, 2 USD an
    order); the share count comes from Yahoo's price, which carries every split up to 2026, and the kit knows only the
    2016-2021 splits, so a share split forward after 2021 reads a price below the one traded then and pays the per-share
    rate when the real order paid the 2 USD minimum (pessimistic: KLAC, CMG, ...). This re-simulates the same signals
    with the commission of every class share at the 2 USD minimum alone (per adjusted unit: 2 x price / the stake
    notional, costs.trade_notional), everything else equal (spread, slippage, swaps, dividends, the stop's quotes). The
    truth lies between the two runs. `bars`: the books (sim.books) or bars of the main run; markets of other classes
    are simulated unchanged. Returns {'base', 'min_commission', 'shares_paying_per_share_rate'} with n, PF, mean R,
    t (daily sums) and PF x1.5 of each run, and the class shares whose median bar pays the per-share rate.
    Give the result to judge.verdict(min_commission=...): results.json and the ledger line carry it."""
    import copy
    bk = sim.books(bars) if isinstance(bars, dict) else bars
    single = not isinstance(bk, dict)
    items = {getattr(bk, "key", None): bk} if single else bk
    alt, binds = {}, []
    for k, b in items.items():
        if _data._C.market_class(k) is None or getattr(b, "comm_q", None) is None:
            alt[k] = b
            continue
        nb = copy.copy(b)
        mc, n_ = float(_data._C.spec(k)["min_commission_per_side"]), float(_data._C.trade_notional(k))
        nb.comm_q = {x: mc * np.asarray(b.mid[x], float) / n_ for x in "ohlc"}
        nb.comm = nb.comm_q["o"]
        alt[k] = nb
        if float(np.median(b.comm_q["o"] - nb.comm_q["o"])) > 0:
            binds.append(k)
    r = dict(rule)
    d0 = r.pop("delay_h", 0.0)
    a = sim.simulate(signals, bk, delay_h=d0, max_wait_h=max_wait_h, **r)
    b2 = sim.simulate(signals, alt[next(iter(alt))] if single else alt, delay_h=d0, max_wait_h=max_wait_h, **r)

    def f(t):
        if not len(t):
            return {"n": 0, "PF": None, "mean_R": None, "t_daily": None, "PF_stress": None}
        day = pd.DatetimeIndex(t.entry_time).tz_convert("UTC").normalize()
        return {"n": int(len(t)), "PF": S.pf(t.R), "mean_R": float(t.R.mean()),
                "t_daily": float(S.t_stat(t.R.groupby(day).sum())), "PF_stress": S.pf(t.R_stress)}
    return {"base": f(a), "min_commission": f(b2), "shares_paying_per_share_rate": sorted(binds),
            "n_class_markets": int(sum(_data._C.market_class(k) is not None for k in items)),
            "note": "sensitivity, not judged: the per-share rate on Yahoo's prices is pessimistic for shares split "
                    "forward after 2021; the minimum alone is the optimistic bound"}


def declared_hash(idea_dir):
    """sha256 of declared.json; raises if it does not match declared.sha256 (first token) or if either is missing.
    judge.verdict calls it itself (bar 'declared_hash')."""
    h = hashlib.sha256(open(os.path.join(idea_dir, "declared.json"), "rb").read()).hexdigest()
    want = open(os.path.join(idea_dir, "declared.sha256")).read().split()[0].strip()
    if h != want:
        raise AssertionError(f"declared.json changed after declaration: {h} != {want}")
    return h
