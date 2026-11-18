"""Trade simulator on hourly bars with FP costs (vectorised numpy; no numba needed).

Signal table: one row per signal, columns `known_at` (UTC, the time the signal could first be known: a value computed
from a bar's close is known at that bar's END), `side` (+1 / -1), and `market` (an FP cost key) when several markets are
simulated together; optional `rule` (one position per market AND rule). The rule (same for every row) is given as
arguments:
  exit   = ("hours", N) | ("clock", "HH:MM", tz) | ("bdays", N)
           hours: first bar opening at or after entry + N h; clock: next occurrence of HH:MM (tz wall clock, Monday to
           Friday) strictly after the entry bar's open; bdays: entry + N business days (pandas BDay, same time of day).
           A scheduled exit that falls where no bar exists (the bar holding it is missing: closure, break, holiday; the
           crypto weekend at FP) is done at the CLOSE of the last bar before (lab/goldlab/data.py exit_index; FP crypto
           'time exit in the closure at the Friday close', lab/COSTS_FP.md).
         | ("event", events, max_hold)  exit on a condition: events = the UTC times at which the exit condition is
           KNOWN to be true (DatetimeIndex, {market: DatetimeIndex}, or the table of an event build); the trade leaves
           at the open of the first bar opening at or after the first event STRICTLY after its entry bar's open
           (reason 'event'; an event in a closure exits at the reopening, never at the close before it), or by
           max_hold = ("hours", N) | ("bdays", N) if that comes first. trades.attrs['events_sha'] binds the events to
           their truncation report (judge.verdict refuses a pass without it).
Pairs: a PairBook (pair_book) is a market like any other in {name: book}; see PairBook and _pair_outcomes for its
observation-based stops and targets and its two-leg costs; the trades get extra columns entry_px_a/b, exit_px_a/b
and stop_frac.
  stop   = ("d20", k) | ("bps", x)   MANDATORY. D20 = mean high-low of the 20 completed 17:00-NY trading days (>= 10 bars)
           before the entry bar opens. Stop and target are set from the fill price (lab/goldlab/sim.py).
  target = None | ("d20", k) | ("bps", x)
  delay_h: entry at the open of the first bar opening at or after known_at + delay_h hours (0 by default).
  mode   : "one" = one position per market and rule (a signal while a trade is open is skipped and counted; the next
           entry must open after the exit bar, lab/goldlab/sim.py no_overlap); among signals entering at the same bar
           the earliest known_at, then the first row, is kept (never the one that exits first); counts
           'overlap_skipped' and, inside it, 'same_bar_skipped'. "every" = every signal taken.
Fills (lab/goldlab/sim.py): long buys the ask, sells the bid; short the reverse. ask = bid + modelled FP spread (bars of
price_is 'bid', Dukascopy) or bid/ask = price -/+ spread/2 (price_is 'mid', Binance). Stop and target checked from the
entry bar on; both touched in one bar -> the stop; on later bars a bar opening beyond the stop fills at its open (stop
slippage), beyond the target at its open (no slippage). A trade whose exit is not inside the data is dropped and
counted (open_at_end).
Three scenarios are simulated from the same signals: gross (mid, no cost), net (FP costs), stress (spread and slippage
x1.5); which signals are taken under mode 'one' is decided on the net scenario and kept for the other two.
Output trade columns: market rule side known_at entry_time exit_time entry_px exit_px stop_px target_px stop_dist d20
reason gross_bp net_bp stress_bp swap_bp R_gross R R_stress hold_h hold_tdays entry_i exit_i sig.
R = net result / stop distance (price units per unit). Skipped counts in trades.attrs['counts']; trades.attrs['signals_sha']
= signals_sha(input table), checked by judge.verdict against the truncation report.
"""
import numpy as np
import pandas as pd

from . import costs as C
from . import data as _data

NS_H = 3_600_000_000_000
BAR_NS = NS_H
GAP_NS = 59 * 60 * 1_000_000_000          # a scheduled exit more than 59 min before the next bar: no bar holds it


class Book:
    """Arrays of one market's hourly bars, with the modelled spread and D20, ready for many simulations."""

    def __init__(self, bars, key, price_is=None, min_day_bars=10):
        C.spec(key)
        if len(bars) == 0:
            raise ValueError(f"{key}: no bars")
        idx = pd.DatetimeIndex(bars.index)
        if idx.tz is None:
            raise ValueError("bars need a tz-aware UTC index")
        if not idx.is_monotonic_increasing or not idx.is_unique:
            raise ValueError("bars index must be increasing and unique")
        if idx.max() >= _data.period_end():
            raise _data.PeriodError(f"{key}: bars at or after {_data.period_end()} (period lock): cut them with data.cut")
        self.key, self.index = key, idx
        self.price_is = price_is or bars.attrs.get("price_is") or "bid"
        self.t = idx.tz_convert("UTC").as_unit("ns").asi8
        o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.s = C.spread(key, o, idx)                                   # base modelled spread per bar (net scenario)
        self.s_close = C.spread(key, c, idx, at="close")                 # at the bar's close (exits before a closure)
        bid = self.price_is == "bid"
        off = self.s / 2 if bid else np.zeros_like(o)
        self.mid = {k: v + off for k, v in (("o", o), ("h", h), ("l", l))}
        self.mid["c"] = c + (self.s_close / 2 if bid else 0.0)
        self._set_d20(idx, h, l, min_day_bars)

    def _set_d20(self, idx, h, l, min_day_bars):
        # D20: completed 17:00-NY trading days with >= min_day_bars bars, known at the end of their last bar
        td = C.trading_day(idx)
        g = pd.DataFrame({"h": h, "l": l, "t": self.t}).groupby(td)
        d = pd.DataFrame({"rng": g["h"].max() - g["l"].min(), "n": g["h"].size(), "end": g["t"].max() + BAR_NS})
        d = d[d.n >= min_day_bars]
        cs = np.r_[0.0, np.cumsum(d.rng.to_numpy())]
        self.d_end, self.d_cs = d.end.to_numpy(np.int64), cs
        self.day_ranges = d

    def d20(self, t_ns):
        k = np.searchsorted(self.d_end, t_ns, side="right")        # days whose end <= t
        out = (self.d_cs[np.clip(k, 0, None)] - self.d_cs[np.clip(k - 20, 0, None)]) / 20.0
        return np.where(k >= 20, out, np.nan)

    def quotes(self, k_spr):
        """bid/ask OHLC of a scenario: mid -/+ k_spr x spread / 2 (lab/goldlab/sim.py apply_spread_mult); the close uses
        the close-of-bar spread."""
        hs = {x: self.s * k_spr / 2 for x in "ohl"}
        hs["c"] = self.s_close * k_spr / 2
        return ({x: self.mid[x] - hs[x] for x in "ohlc"}, {x: self.mid[x] + hs[x] for x in "ohlc"})


class PairBook(Book):
    """A hedged pair as ONE synthetic market (lead's ruling of 2026-11-18): two legs of equal notional at entry.
    kind 'ratio': P = mid_a / mid_b, long the pair = long a, short b; 'product': P = mid_a x mid_b (EURCHF = EURUSD x
    USDCHF), long the pair = long a, long b. The pair's name is registered in kit.costs (costs.spec(name) works).
    Bars: the hours where BOTH legs have a bar (never a leg's stale price). The pair's path inside an hour is unknown, so
    it is OBSERVED at each bar's open and close only: open = P of the legs' opens, close = P of the legs' closes,
    high / low = max / min of open and close (a leg's own wick is never combined with the other leg's). D20 = mean of
    the pair's own daily range (17:00 New York days) from these observed prices, known at each day's end, as Book.
    Costs per leg, added (lab conventions of each leg: lab/goldlab/sim.py fills, lab/build_fp_frames.py spread shape,
    lab/COSTS_FP.md): each leg's fill at its own quote (spread in bp of its reference price x its hour-of-week shape at
    the bar's open, close-of-bar shape at a close) and slippage; swap per night = the rate of the side held on each leg.
    Relative spread of the pair = spread_a / price_a + spread_b / price_b (self.s, in P units, for reports).
    The result is the EXACT two-leg result per unit of ONE leg's notional (sim._pair_outcomes), not P_exit / P_entry - 1."""

    def __init__(self, name, book_a, book_b, kind="ratio", min_day_bars=10):
        if isinstance(book_a, PairBook) or isinstance(book_b, PairBook):
            raise ValueError("a leg of a pair is one market, not a pair")
        sp = C.register_pair(name, book_a.key, book_b.key, kind)
        self.key, self.kind = name, kind
        self.legs, self.leg_keys = (book_a, book_b), (book_a.key, book_b.key)
        self.leg_sides = sp["pair"]["sides"]
        self.swap_triple = sp["swap_triple"]
        t = np.intersect1d(book_a.t, book_b.t)
        if len(t) == 0:
            raise ValueError(f"{name}: the legs share no hour")
        self.t = t
        self.index = pd.DatetimeIndex(t.astype("datetime64[ns]")).tz_localize("UTC")
        self.price_is = "pair"
        self.leg = []
        for bk in self.legs:
            i = np.searchsorted(bk.t, t)
            self.leg.append({"mid": {x: bk.mid[x][i] for x in "ohlc"}, "s": bk.s[i], "s_close": bk.s_close[i]})
        f = (lambda x, y: x / y) if kind == "ratio" else (lambda x, y: x * y)
        a, b = self.leg
        po, pc = f(a["mid"]["o"], b["mid"]["o"]), f(a["mid"]["c"], b["mid"]["c"])
        self.combine = f
        self.mid = {"o": po, "c": pc, "h": np.maximum(po, pc), "l": np.minimum(po, pc)}
        self.s = po * (a["s"] / a["mid"]["o"] + b["s"] / b["mid"]["o"])
        self.s_close = pc * (a["s_close"] / a["mid"]["c"] + b["s_close"] / b["mid"]["c"])
        self._set_d20(self.index, self.mid["h"], self.mid["l"], min_day_bars)

    def quotes(self, k_spr):
        raise NotImplementedError("a pair is quoted per leg (sim._pair_outcomes)")


def pair_book(name, key_a, key_b, bars_a, bars_b, kind="ratio", min_day_bars=10):
    """A hedged pair usable wherever a Book is (simulate, outcomes, stats.null_test, judge, checks): name = its market
    name in the signal table and the trades (e.g. 'eurusd/gbpusd'); bars_a / bars_b: the legs' bars (or Books) of FP
    keys key_a, key_b. Several pairs in one {name: PairBook} dict form a basket of pairs (CHARTER 'Rulings' (a))."""
    ba = bars_a if isinstance(bars_a, Book) else Book(bars_a, key_a)
    bb = bars_b if isinstance(bars_b, Book) else Book(bars_b, key_b)
    if ba.key != key_a or bb.key != key_b:
        raise ValueError("the legs' Books are of other markets than key_a / key_b")
    return PairBook(name, ba, bb, kind, min_day_bars)


# ------------------------------------------------------------------ exits on a condition (events)
def _events_canon(events):
    """{market or '*': sorted unique int64 ns} from a DatetimeIndex (any market), {market: DatetimeIndex}, or a table
    with column known_at (and optionally market), as checks.truncation_test builds it."""
    def ns(x):
        x = pd.DatetimeIndex(x)
        if len(x) and x.tz is None:
            raise ValueError("event times must be tz-aware UTC")
        return np.unique((x.tz_convert("UTC") if x.tz is not None else x.tz_localize("UTC")).as_unit("ns").asi8)
    if isinstance(events, pd.DataFrame):
        if "market" in events:
            return {str(k): ns(g["known_at"]) for k, g in events.groupby("market", sort=True)}
        return {"*": ns(events["known_at"])}
    if isinstance(events, dict):
        return {str(k): ns(v) for k, v in events.items()}
    if isinstance(events, (pd.DatetimeIndex, pd.Series, np.ndarray, list)):
        return {"*": ns(events)}
    raise ValueError("events: a DatetimeIndex, {market: DatetimeIndex} or a table with known_at [, market]")


def events_sha(events):
    """sha256 of event times (per market), order-free: binds an event truncation report (checks.truncation_test on the
    event build) to the events a rule exited on (trades.attrs['events_sha'], checked by judge.verdict)."""
    import hashlib
    h = hashlib.sha256()
    for k, v in sorted(_events_canon(events).items()):
        h.update(k.encode() + b"\0" + v.astype(np.int64).tobytes() + b"\1")
    return h.hexdigest()


def _ns_sha(v):
    import hashlib
    return hashlib.sha256(np.asarray(v, np.int64).tobytes()).hexdigest()


def events_by_key(events):
    """{market or '*': sha256 of that key's sorted unique event times}: what an event truncation report stores so that
    judge.verdict can compare it with the events each simulated market actually used (verifier V2: the same times given
    as a table without market or as {market: times} are the same events)."""
    return {k: _ns_sha(v) for k, v in _events_canon(events).items()}


def events_used(events, markets):
    """{market: sha256 of the event times that market's exits use} (the market's own set, else '*')."""
    canon = _events_canon(events)
    out = {}
    for m in markets:
        v = canon.get(str(m), canon.get("*"))
        out[str(m)] = None if v is None else _ns_sha(v)
    return out


def _norm(x):
    if isinstance(x, (bool, np.bool_)) or x is None:
        return x if x is None else bool(x)
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    if isinstance(x, (tuple, list)):
        return [_norm(y) for y in x]
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    return str(x)


def exit_key(exit, stop, target, markets):
    """sha256 of the exit rule as the trades of `markets` used it: (exit, stop, target), with an event exit resolved to
    the event times each market used. simulate stores it in trades.attrs['exit_key'] (over the markets that have
    trades), stats.null_test in its result; judge.verdict fails the null bar when they differ (verifier V4: a null run
    with another exit, stop, target or other events than the main is not the main's null)."""
    import hashlib
    import json
    mk = sorted(str(m) for m in markets)
    if exit[0] == "event":
        ex = ["event", events_used(exit[1], mk), _norm(tuple(exit[2]) if len(exit) > 2 and exit[2] is not None else None)]
    else:
        ex = _norm(tuple(exit))
    blob = json.dumps({"exit": ex, "stop": _norm(stop), "target": _norm(target), "markets": mk}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def event_exit(events, max_hold):
    """exit=('event', events, max_hold) from an event table built by a function of the data (columns known_at = when
    the exit condition is KNOWN to be true, optional market): the form simulate and the null take."""
    return ("event", events, tuple(max_hold))


def _exit_plan(t, eic, exit, key=None):
    """Exit bar of entries at bar indices eic: (j, closure, label). j = the first bar opening at or after the exit time
    (time exit at its open), closure = no bar holds a scheduled exit (exit at the close of bar j - 1, lab/goldlab/data.py
    exit_index). Event exits (exit = ('event', events, max_hold)): the first event time STRICTLY after the entry bar's
    open, E; the trade leaves at the open of the first bar opening at or after E (label 'event'), or by max_hold
    (('hours', N) | ('bdays', N) | ('clock', ...)) if that exit comes first. An event that falls where no bar exists
    (a closure, the crypto weekend) is NOT done at the close before it, which would act before the event is known: the
    trade leaves at the reopening bar's open."""
    N = len(t)
    if exit[0] != "event":
        X = _sched_exit(t[eic], exit)
        j = np.searchsorted(t, X, side="left")
        end = j >= N
        jc = np.clip(j, 0, N - 1)
        closure = ~end & ((t[jc] - X) > GAP_NS)
        return j, closure, np.where(closure, "time_close", "time").astype(object)
    if len(exit) != 3 or exit[2] is None or exit[2][0] == "event":
        raise ValueError("event exit: ('event', events, max_hold) with max_hold = ('hours', N) or ('bdays', N)")
    canon = _events_canon(exit[1])
    ev = canon.get(str(key), canon.get("*"))
    if ev is None:
        raise ValueError(f"event exit: no events given for market {key} (give an empty DatetimeIndex if none)")
    jm, cm, wm = _exit_plan(t, eic, tuple(exit[2]))
    big = np.iinfo(np.int64).max
    k = np.searchsorted(ev, t[eic], side="right")                     # first event strictly after the entry bar's open
    E = np.where(k < len(ev), ev[np.clip(k, 0, max(len(ev) - 1, 0))] if len(ev) else big, big)
    je = np.searchsorted(t, E, side="left")
    tm = np.where(jm >= N, big, np.where(cm, t[np.clip(jm - 1, 0, N - 1)] + BAR_NS, t[np.clip(jm, 0, N - 1)]))
    te = np.where(je >= N, big, t[np.clip(je, 0, N - 1)])
    use_e = (je < N) & (te <= tm)
    return (np.where(use_e, je, jm), np.where(use_e, False, cm), np.where(use_e, "event", wm).astype(object))


def _sched_exit(t_entry_ns, exit):
    kind = exit[0]
    if kind == "hours":
        return t_entry_ns + int(round(float(exit[1]) * NS_H))
    ent = pd.DatetimeIndex(t_entry_ns.astype("datetime64[ns]")).tz_localize("UTC")
    if kind == "bdays":
        return (ent + pd.offsets.BDay(int(exit[1]))).as_unit("ns").asi8
    if kind == "clock":
        tz = exit[2] if len(exit) > 2 else "UTC"
        hh, mm = (int(x) for x in exit[1].split(":"))
        loc = ent.tz_convert(tz).tz_localize(None)
        cand = loc.normalize() + pd.Timedelta(hours=hh, minutes=mm)
        cand = cand.where(cand > loc, cand + pd.Timedelta(days=1))
        for _ in range(3):
            cand = cand.where(cand.dayofweek < 5, cand + pd.Timedelta(days=1))
        return cand.tz_localize(tz, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC").as_unit("ns").asi8
    raise ValueError(f"unknown exit rule {exit}")


def _dist(spec, d20, mid_open):
    if spec is None:
        return np.full(len(d20), np.nan)
    kind, x = spec[0], float(spec[1])
    if kind == "d20":
        return x * d20
    if kind == "bps":
        return x * 1e-4 * mid_open
    raise ValueError(f"unknown distance {spec}")


def outcomes(book, ei, side, exit, stop, target=None, scenarios=("gross", "net", "stress"), chunk_cells=4_000_000):
    """Every-signal outcomes of entries at bar indices `ei` (open) with `side`. Returns dict of arrays (one entry per
    input; ok=False where dropped) with the per-scenario prices and R."""
    if stop is None:
        raise ValueError("a protective stop is mandatory")
    if isinstance(book, PairBook):
        return _pair_outcomes(book, ei, side, exit, stop, target, scenarios, chunk_cells)
    ei = np.asarray(ei, np.int64)
    side = np.asarray(side, np.int64)
    n, N, t = len(ei), len(book.t), book.t
    out = {"ok": np.zeros(n, bool), "why": np.full(n, "", object)}
    if n == 0:
        return out
    valid = (ei >= 0) & (ei < N)
    eic = np.clip(ei, 0, N - 1)
    j, closure, xlabel = _exit_plan(t, eic, exit, book.key)
    end = j >= N
    jc = np.clip(j, 0, N - 1)
    last = np.maximum(j - 1, eic)                                     # last bar scanned for stop/target
    d20 = book.d20(t[eic])
    mo = book.mid["o"][eic]
    sd = _dist(stop, d20, mo)
    td = _dist(target, d20, mo)
    ok = valid & ~end & np.isfinite(sd) & (sd > 0)
    out["why"][~valid] = "no_bar"
    out["why"][valid & end] = "open_at_end"
    out["why"][valid & ~end & ~(np.isfinite(sd) & (sd > 0))] = "no_d20"
    out.update(ok=ok, entry_i=eic, d20=d20, stop_dist=sd)
    L = np.where(ok, last - eic + 1, 1)
    spec = C.spec(book.key)
    for sc in scenarios:
        k_spr, k_slip, with_swap = C.SCENARIOS[sc]
        bid, ask = book.quotes(k_spr)
        sm, ss = C.slip(book.key, "mkt", k_slip), C.slip(book.key, "stop", k_slip)
        fill = np.where(side > 0, ask["o"][eic] * (1 + sm), bid["o"][eic] * (1 - sm))
        st = fill - side * sd
        tg = fill + side * td
        xi = np.where(closure, j - 1, jc).astype(np.int64)
        xpx = np.where(closure,
                       np.where(side > 0, bid["c"][np.clip(j - 1, 0, N - 1)] * (1 - sm), ask["c"][np.clip(j - 1, 0, N - 1)] * (1 + sm)),
                       np.where(side > 0, bid["o"][jc] * (1 - sm), ask["o"][jc] * (1 + sm)))
        xt = np.where(closure, t[np.clip(j - 1, 0, N - 1)] + BAR_NS, t[jc])
        why = xlabel.copy()
        order = np.argsort(-L, kind="stable")            # longest windows first: chunk size from the first
        pos = 0
        while pos < n:
            Lmax = int(L[order[pos]])
            m = max(1, chunk_cells // max(Lmax, 1))
            sel = order[pos:pos + m]
            Lm = int(L[sel].max())
            off = np.arange(Lm)
            bi = np.minimum(eic[sel, None] + off[None, :], N - 1)
            inwin = off[None, :] < L[sel, None]
            s1 = side[sel, None]
            lo = np.where(s1 > 0, bid["l"][bi], ask["l"][bi])
            hi = np.where(s1 > 0, bid["h"][bi], ask["h"][bi])
            opn = np.where(s1 > 0, bid["o"][bi], ask["o"][bi])
            stp, tgt = st[sel, None], tg[sel, None]
            hs = inwin & np.where(s1 > 0, lo <= stp, hi >= stp)
            ht = inwin & np.isfinite(tgt) & np.where(s1 > 0, hi >= tgt, lo <= tgt)
            fs = np.where(hs.any(1), hs.argmax(1), Lm + 1)
            ft = np.where(ht.any(1), ht.argmax(1), Lm + 1)
            r = np.arange(len(sel))
            take_s = (fs <= Lm) & (fs <= ft)
            take_t = (ft <= Lm) & ~take_s
            b_s = np.minimum(fs, Lm - 1)
            o_s = opn[r, b_s]
            px_s = np.where(b_s == 0, st[sel], np.where(side[sel] > 0, np.minimum(st[sel], o_s), np.maximum(st[sel], o_s)))
            px_s = px_s * np.where(side[sel] > 0, 1 - ss, 1 + ss)
            b_t = np.minimum(ft, Lm - 1)
            o_t = opn[r, b_t]
            px_t = np.where(b_t == 0, tg[sel], np.where(side[sel] > 0, np.maximum(tg[sel], o_t), np.minimum(tg[sel], o_t)))
            gap_s = (b_s > 0) & np.where(side[sel] > 0, o_s < st[sel], o_s > st[sel])
            xpx[sel] = np.where(take_s, px_s, np.where(take_t, px_t, xpx[sel]))
            xi[sel] = np.where(take_s, eic[sel] + b_s, np.where(take_t, eic[sel] + b_t, xi[sel]))
            xt[sel] = np.where(take_s | take_t, t[np.minimum(xi[sel], N - 1)] + BAR_NS, xt[sel])
            why[sel] = np.where(take_s, np.where(gap_s, "stop_gap", "stop"), np.where(take_t, "target", why[sel]))
            pos += m
        et = pd.DatetimeIndex(t[eic].astype("datetime64[ns]")).tz_localize("UTC")
        xtt = pd.DatetimeIndex(xt.astype("datetime64[ns]")).tz_localize("UTC")
        sw = C.swap(book.key, side, fill, et, xtt) if with_swap else np.zeros(n)
        pnl = side * (xpx - fill) - sw
        out[sc] = {"fill": fill, "exit": xpx, "swap": sw, "pnl": pnl, "R": pnl / sd, "bp": pnl / fill * 1e4,
                   "exit_i": xi, "exit_t": xt, "reason": why, "stop_px": st, "target_px": tg}
    return out


def _pair_outcomes(book, ei, side, exit, stop, target=None, scenarios=("gross", "net", "stress"), chunk_cells=4_000_000):
    """outcomes() of a PairBook. Per trade: legs' sides = pair side x book.leg_sides; each leg filled at the entry bar's
    open at its own quote and market slippage. The trade's result per unit of ONE leg's notional is the EXACT two-leg
    result sum_legs side_leg x (exit_leg / fill_leg - 1) - swaps (not P_exit / P_entry - 1: for a ratio that is
    (r_a - r_b) / (1 + r_b), off by the second-order term (r_a - r_b) r_b / (1 + r_b), measured in test_kit P1).
    Stop and target are distances in P units (D20 of P, or bp of P) turned into fractions of the entry bar's mid P;
    they are judged on the OBSERVED liquidation result (both legs at their exit-side quotes, no slippage) at each bar's
    open (from the bar after the entry) and close, in time order; the first observation at or beyond a level is a
    market exit of both legs at that observation's quotes (a robot computes the pair's result from both legs and closes
    both when it sees the level crossed): stop = both legs' stop slippage ('stop_gap' at an open, 'stop' at a close),
    target = both legs' market slippage ('target'). So R can be worse than -1 and a target is never filled at its level.
    Time and event exits at the exit bar's open (market slippage), a scheduled exit in a closure at the close of the
    last bar before (close-of-bar spread shape of each leg). Swaps: each leg the rate of the side it holds, nights of the
    pair (the legs share the triple weekday). pnl in P units = result x mid P at entry, so R = result / (stop distance
    / mid P) = pnl / stop_dist, bp = result x 1e4. Extra per scenario: 'legs' (fills and exits) and 'stop_frac'."""
    ei = np.asarray(ei, np.int64)
    side = np.asarray(side, np.int64)
    n, N, t = len(ei), len(book.t), book.t
    out = {"ok": np.zeros(n, bool), "why": np.full(n, "", object)}
    if n == 0:
        return out
    valid = (ei >= 0) & (ei < N)
    eic = np.clip(ei, 0, N - 1)
    j, closure, xlabel = _exit_plan(t, eic, exit, book.key)
    end = j >= N
    jc = np.clip(j, 0, N - 1)
    jp = np.clip(j - 1, 0, N - 1)
    last = np.maximum(j - 1, eic)
    d20 = book.d20(t[eic])
    mo = book.mid["o"][eic]
    sd = _dist(stop, d20, mo)
    td = _dist(target, d20, mo)
    ok = valid & ~end & np.isfinite(sd) & (sd > 0)
    out["why"][~valid] = "no_bar"
    out["why"][valid & end] = "open_at_end"
    out["why"][valid & ~end & ~(np.isfinite(sd) & (sd > 0))] = "no_d20"
    out.update(ok=ok, entry_i=eic, d20=d20, stop_dist=sd)
    sdf, tdf = sd / mo, td / mo
    L = np.where(ok, last - eic + 1, 1)
    ls = [side * s for s in book.leg_sides]                                  # each leg's side per trade
    et = pd.DatetimeIndex(t[eic].astype("datetime64[ns]")).tz_localize("UTC")
    for sc in scenarios:
        k_spr, k_slip, with_swap = C.SCENARIOS[sc]
        Q = []
        for leg, key, s in zip(book.leg, book.leg_keys, ls):
            ho, hc = leg["s"] * k_spr / 2, leg["s_close"] * k_spr / 2
            q = {"bid": {"o": leg["mid"]["o"] - ho, "c": leg["mid"]["c"] - hc},
                 "ask": {"o": leg["mid"]["o"] + ho, "c": leg["mid"]["c"] + hc},
                 "sm": C.slip(key, "mkt", k_slip), "ss": C.slip(key, "stop", k_slip), "side": s}
            q["fill"] = np.where(s > 0, q["ask"]["o"][eic] * (1 + q["sm"]), q["bid"]["o"][eic] * (1 - q["sm"]))
            # exit at market at the open of jc, or at the close of j - 1 (scheduled exit in a closure)
            q["x"] = np.where(closure,
                              np.where(s > 0, q["bid"]["c"][jp] * (1 - q["sm"]), q["ask"]["c"][jp] * (1 + q["sm"])),
                              np.where(s > 0, q["bid"]["o"][jc] * (1 - q["sm"]), q["ask"]["o"][jc] * (1 + q["sm"])))
            Q.append(q)
        xi = np.where(closure, j - 1, jc).astype(np.int64)
        xt = np.where(closure, t[jp] + BAR_NS, t[jc])
        why = xlabel.copy()
        order = np.argsort(-L, kind="stable")
        pos = 0
        while pos < n:
            Lmax = int(L[order[pos]])
            m = max(1, chunk_cells // max(4 * Lmax, 1))
            sel = order[pos:pos + m]
            Lm = int(L[sel].max())
            off = np.arange(Lm)
            bi = np.minimum(eic[sel, None] + off[None, :], N - 1)
            inwin = off[None, :] < L[sel, None]
            res = np.zeros((len(sel), 2 * Lm))                               # observations: open, close of each bar
            for q in Q:
                s1 = q["side"][sel, None]
                f1 = q["fill"][sel, None]
                res[:, 0::2] += s1 * (np.where(s1 > 0, q["bid"]["o"][bi], q["ask"]["o"][bi]) / f1 - 1)
                res[:, 1::2] += s1 * (np.where(s1 > 0, q["bid"]["c"][bi], q["ask"]["c"][bi]) / f1 - 1)
            obs = np.repeat(inwin, 2, axis=1)
            obs[:, 0] = False                                                # the entry bar's open is the entry
            hs = obs & (res <= -sdf[sel, None])
            ht = obs & np.isfinite(tdf[sel, None]) & (res >= tdf[sel, None])
            big = 2 * Lm + 1
            fs = np.where(hs.any(1), hs.argmax(1), big)
            ft = np.where(ht.any(1), ht.argmax(1), big)
            take_s = (fs < big) & (fs <= ft)
            take_t = (ft < big) & ~take_s
            k = np.where(take_s, fs, ft)
            k = np.minimum(k, 2 * Lm - 1)
            b = eic[sel] + k // 2
            b = np.minimum(b, N - 1)
            at_open = (k % 2) == 0
            hit = take_s | take_t
            for q in Q:
                s1 = q["side"][sel]
                sl = np.where(take_s, q["ss"], q["sm"])
                qq = np.where(at_open, np.where(s1 > 0, q["bid"]["o"][b], q["ask"]["o"][b]),
                              np.where(s1 > 0, q["bid"]["c"][b], q["ask"]["c"][b]))
                px = qq * np.where(s1 > 0, 1 - sl, 1 + sl)
                q["x"][sel] = np.where(hit, px, q["x"][sel])
            xi[sel] = np.where(hit, b, xi[sel])
            xt[sel] = np.where(hit, t[b] + np.where(at_open, 0, BAR_NS), xt[sel])
            why[sel] = np.where(take_s, np.where(at_open, "stop_gap", "stop"), np.where(take_t, "target", why[sel]))
            pos += m
        xtt = pd.DatetimeIndex(xt.astype("datetime64[ns]")).tz_localize("UTC")
        swf = np.zeros(n)
        if with_swap:
            nights = C.swap_nights(et, xtt, book.swap_triple)
            for q, key in zip(Q, book.leg_keys):
                spk = C.spec(key)
                swf = swf + np.where(q["side"] > 0, spk["swap_long"], spk["swap_short"]) / 360.0 * nights
        result = sum(q["side"] * (q["x"] / q["fill"] - 1) for q in Q) - swf
        pfill = book.combine(Q[0]["fill"], Q[1]["fill"])
        pexit = book.combine(Q[0]["x"], Q[1]["x"])
        out[sc] = {"fill": pfill, "exit": pexit, "swap": swf * pfill, "pnl": result * mo, "R": result / sdf,
                   "bp": result * 1e4, "exit_i": xi, "exit_t": xt, "reason": why, "stop_px": pfill - side * sd,
                   "target_px": pfill + side * td, "stop_frac": sdf,
                   "legs": {"fill_a": Q[0]["fill"], "fill_b": Q[1]["fill"], "exit_a": Q[0]["x"], "exit_b": Q[1]["x"]}}
    return out


def _one_position(entry_i, exit_i, groups, order=None):
    """Greedy one-position filter within each group (lab: skip if entry bar <= last exit bar). Signals are visited by
    entry bar, then by `order` (known_at, then the row order of the signal table): NEVER by exit, which is future
    information (verifier V1: keeping the first exit among same-bar signals keeps the winner when the target is nearer
    than the stop). Returns (keep, same_bar) where same_bar marks skipped signals whose entry bar is the entry bar of a
    kept trade of the same group."""
    n = len(entry_i)
    keep = np.zeros(n, bool)
    same = np.zeros(n, bool)
    order = np.arange(n) if order is None else np.asarray(order)
    last, first_e = {}, {}
    for k in np.lexsort((np.arange(n), order, entry_i)):
        g = groups[k]
        if entry_i[k] > last.get(g, -1):
            keep[k] = True
            last[g] = exit_i[k]
            first_e[g] = entry_i[k]
        elif first_e.get(g) == entry_i[k]:
            same[k] = True
    return keep, same


def signals_sha(signals):
    """sha256 of a signal table's (known_at, side) pairs, order-free: binds a truncation report to the signals that
    were simulated (checks.truncation_test stores it, simulate stores it, judge.verdict compares them)."""
    import hashlib
    ka = pd.DatetimeIndex(signals["known_at"])
    ka = (ka.tz_convert("UTC") if ka.tz is not None else ka.tz_localize("UTC")).as_unit("ns").asi8
    sd = np.asarray(signals["side"], np.int64)
    o = np.lexsort((sd, ka))
    return hashlib.sha256(np.stack([ka[o], sd[o]]).astype(np.int64).tobytes()).hexdigest()


def simulate(signals, bars, exit, stop, target=None, delay_h=0.0, mode="one", max_wait_h=None, market=None):
    """Simulate a signal table. `bars`: one market's bars (give `market`) or {fp_key: bars} (signals need a `market`
    column), or {fp_key: Book}. Returns the trades DataFrame (attrs['counts'] = skipped counts per market)."""
    sig = signals.copy()
    if market is not None:
        sig["market"] = market
        bars = {market: bars}
    if "market" not in sig:
        raise ValueError("signals need a 'market' column (or pass market=)")
    if "rule" not in sig:
        sig["rule"] = "r"
    sig["sig"] = np.arange(len(sig))
    ka = pd.DatetimeIndex(sig["known_at"])
    if ka.tz is None:
        raise ValueError("known_at must be tz-aware UTC")
    if not set(np.unique(sig["side"])) <= {-1, 1}:
        raise ValueError("side must be +1 or -1")
    frames, counts = [], {}
    for mk, g in sig.groupby("market", sort=True):
        bk = bars[mk] if isinstance(bars[mk], Book) else Book(bars[mk], mk)
        tq = pd.DatetimeIndex(g["known_at"]).tz_convert("UTC").as_unit("ns").asi8 + int(round(delay_h * NS_H))
        ei = np.searchsorted(bk.t, tq, side="left")
        stale = np.zeros(len(g), bool)
        if max_wait_h is not None:
            stale = (ei < len(bk.t)) & ((bk.t[np.clip(ei, 0, len(bk.t) - 1)] - tq) > max_wait_h * NS_H)
        ei = np.where(stale, len(bk.t), ei)
        o = outcomes(bk, ei, g["side"].to_numpy(), exit, stop, target)
        cnt = {"signals": int(len(g)), "stale": int(stale.sum())}
        for w in ("no_bar", "open_at_end", "no_d20"):
            cnt[w] = int(((o["why"] == w) & ~stale).sum())
        okm = o["ok"]
        n = o["net"]
        keep = okm.copy()
        if mode == "one":
            idx = np.flatnonzero(okm)
            kk, same = _one_position(o["entry_i"][idx], n["exit_i"][idx], g["rule"].to_numpy()[idx], order=tq[idx])
            keep = np.zeros(len(g), bool)
            keep[idx[kk]] = True
            cnt["overlap_skipped"] = int(len(idx) - kk.sum())
            cnt["same_bar_skipped"] = int(same.sum())   # part of overlap_skipped: another signal took that very bar
        elif mode != "every":
            raise ValueError("mode is 'one' or 'every'")
        cnt["taken"] = int(keep.sum())
        counts[mk] = cnt
        if not keep.any():
            continue
        f = lambda a: np.asarray(a)[keep]  # noqa: E731
        ent = pd.DatetimeIndex(bk.t[f(o["entry_i"])].astype("datetime64[ns]")).tz_localize("UTC")
        ext = pd.DatetimeIndex(f(n["exit_t"]).astype("datetime64[ns]")).tz_localize("UTC")
        tr = pd.DataFrame({
            "market": mk, "rule": f(g["rule"]), "side": f(g["side"]).astype(int), "known_at": f(g["known_at"]),
            "entry_time": ent, "exit_time": ext, "entry_px": f(n["fill"]), "exit_px": f(n["exit"]),
            "stop_px": f(n["stop_px"]), "target_px": f(n["target_px"]), "stop_dist": f(o["stop_dist"]), "d20": f(o["d20"]),
            "reason": f(n["reason"]), "gross_bp": f(o["gross"]["bp"]), "net_bp": f(n["bp"]), "stress_bp": f(o["stress"]["bp"]),
            "swap_bp": f(n["swap"]) / f(n["fill"]) * 1e4, "R_gross": f(o["gross"]["R"]), "R": f(n["R"]),
            "R_stress": f(o["stress"]["R"]), "entry_i": f(o["entry_i"]), "exit_i": f(n["exit_i"]), "sig": f(g["sig"])})
        tr["hold_h"] = (tr.exit_time - tr.entry_time).dt.total_seconds() / 3600
        tr["hold_tdays"] = C.held_tdays(tr.entry_time, tr.exit_time)
        if isinstance(bk, PairBook):                      # both legs' prices (net scenario) for hand checks and sizing
            for k_ in ("fill_a", "fill_b", "exit_a", "exit_b"):
                tr[{"fill_a": "entry_px_a", "fill_b": "entry_px_b", "exit_a": "exit_px_a", "exit_b": "exit_px_b"}[k_]] = \
                    f(n["legs"][k_])
            tr["stop_frac"] = f(n["stop_frac"])
        frames.append(tr)
    cols = ["market", "rule", "side", "known_at", "entry_time", "exit_time", "entry_px", "exit_px", "stop_px", "target_px",
            "stop_dist", "d20", "reason", "gross_bp", "net_bp", "stress_bp", "swap_bp", "R_gross", "R", "R_stress",
            "entry_i", "exit_i", "sig", "hold_h", "hold_tdays"]
    out = pd.concat(frames, ignore_index=True).sort_values(["entry_time", "market"]).reset_index(drop=True) if frames \
        else pd.DataFrame(columns=cols)
    out.attrs["counts"] = counts
    out.attrs["signals_sha"] = signals_sha(signals)
    ex = exit
    if exit[0] == "event":                            # bound to the event build's truncation report by judge.verdict
        out.attrs["events_sha"] = events_sha(exit[1])
        out.attrs["events_used"] = events_used(exit[1], sorted(sig["market"].astype(str).unique()))
        ne = sum(len(v) for v in _events_canon(exit[1]).values())
        ex = ("event", f"{ne} event times, sha256 {out.attrs['events_sha'][:16]}", tuple(exit[2]))
    out.attrs["exit_key"] = exit_key(exit, stop, target, sorted(out["market"].astype(str).unique()) if len(out) else [])
    out.attrs["rule"] = {"exit": ex, "stop": stop, "target": target, "delay_h": delay_h, "mode": mode}
    return out


def books(bars_by_market):
    """{key: Book} once, to reuse across configurations and the null (saves the spread and D20 work)."""
    return {k: (v if isinstance(v, Book) else Book(v, k)) for k, v in bars_by_market.items()}
