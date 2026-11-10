"""Conservative trade simulator on M1 bid/ask bars.

Each order is one row of a DataFrame `orders` with columns:

  entry_i    int    M1 index where the order becomes active (use data.entry_index)
  side       +1 long / -1 short
  etype      0 = market at OPEN of bar entry_i
             1 = stop entry at `level` (buy-stop above / sell-stop below)
             2 = limit entry at `level`
  level      float  entry level for etype 1/2 (NaN for market)
  expiry_i   int    last M1 index where a pending order may fill (etype 1/2)
  stop       float  ABSOLUTE initial stop price (or NaN and give stop_dist)
  stop_dist  float  stop distance from fill price (used if stop is NaN)
  target     float  ABSOLUTE take-profit (NaN = none)
  target_dist float distance from fill (used if target NaN; NaN = none)
  exit_i     int    forced exit at OPEN of this M1 bar (time stop). -1 = none
  trail      float  trailing-stop distance (NaN = none); updated at bar close, used next bar
  be         float  move stop to entry once favourable excursion >= be (NaN = none)

Every trade MUST have a stop (stop or stop_dist).

Fill rules (pessimistic):
  * longs buy at ASK, sell at BID; shorts sell at BID, buy back at ASK.
  * stop fills (stop entries, stop-loss exits) pay slip_bps of price; plain market fills (entry at
    a bar open, time exits) pay slip_mkt_bps (defaults to slip_bps); limit/target fills pay none.
  * gaps: stop entries fill at the worse of level/open; stops exit at worse of stop/open.
  * if stop and target are both inside the same bar -> STOP is assumed first.
  * on the fill bar of a stop entry the stop can be hit; the target can be hit only if the
    path is forced (open below level <= target <= high). Limit entries can't hit target on
    their fill bar.
  * trailing / break-even stops are updated with the bar's extreme AFTER the bar closes.
Costs added afterwards: commission per unit round-trip, overnight swap per 17:00 NY rollover
(one rollover counts triple: Wednesday by default, `Costs.swap_triple`), as an annual % of price.
"""
from dataclasses import dataclass

import numba as nb
import numpy as np
import pandas as pd

from .data import trading_day

STOP, TARGET, TIME, TRAIL, EOD, NOFILL, SKIP, GAP = 0, 1, 2, 3, 4, 5, 6, 7
REASONS = {0: "stop", 1: "target", 2: "time", 3: "trail", 4: "eod", 5: "nofill", 6: "skip", 7: "gap"}


@dataclass
class Costs:
    commission: float = 0.07       # per unit (oz) round trip  (~$7 / lot of 100 oz)
    slip_bps: float = 1.5          # per side on STOP fills (stop entries, stop-loss exits); 1.5 bp = $0.60 at $4000
    slip_mkt_bps: float = -1.0     # per side on plain MARKET fills (entry at bar open, time exit); < 0 = same as slip_bps
    swap_long: float = 0.05        # annual cost of holding long overnight (5 %/yr)
    swap_short: float = 0.02       # annual cost of holding short overnight
    spread_mult: float = 1.0       # stress test: multiply the bid/ask spread
    swap_triple: str = "Wed"       # rollover that counts three nights ("Wed": FX / metals; "Fri": FP Markets indices, crypto)


COSTS = {
    "xauusd": Costs(),
    "eurusd": Costs(commission=0.0, slip_bps=0.2, swap_long=0.02, swap_short=0.02),
    "gbpusd": Costs(commission=0.0, slip_bps=0.3, swap_long=0.02, swap_short=0.02),
    "usdjpy": Costs(commission=0.0, slip_bps=0.3, swap_long=0.02, swap_short=0.04),
    "deuidxeur": Costs(commission=0.0, slip_bps=0.5, swap_long=0.05, swap_short=0.02),
    "lightcmdusd": Costs(commission=0.0, slip_bps=1.0, swap_long=0.05, swap_short=0.05),
}


@nb.njit(cache=True)
def _run(bo, bh, bl, bc, ao, ah, al, ac,
         entry_i, side, etype, level, expiry_i, stop, stop_dist, target, target_dist,
         exit_i, trail, be, slip, slip_m, no_overlap,
         fill_i, fill_px, x_i, x_px, reason, init_stop, mfe, mae):
    N = len(bo)
    last_exit = -1
    for k in range(len(entry_i)):
        i0 = entry_i[k]
        if i0 >= N or i0 < 0:
            reason[k] = NOFILL
            continue
        if no_overlap and i0 <= last_exit:
            reason[k] = SKIP
            continue
        s = side[k]
        fi = -1
        fp = np.nan
        et = etype[k]
        if et == 0:
            fi = i0
            fp = ao[i0] * (1 + slip_m) if s > 0 else bo[i0] * (1 - slip_m)
        else:
            lv = level[k]
            jmax = min(expiry_i[k], N - 1)
            for i in range(i0, jmax + 1):
                if et == 1:
                    if s > 0 and ah[i] >= lv:
                        fi = i
                        fp = max(lv, ao[i]) * (1 + slip)
                        break
                    if s < 0 and bl[i] <= lv:
                        fi = i
                        fp = min(lv, bo[i]) * (1 - slip)
                        break
                else:
                    if s > 0 and al[i] <= lv:
                        fi = i
                        fp = min(lv, ao[i])
                        break
                    if s < 0 and bh[i] >= lv:
                        fi = i
                        fp = max(lv, bo[i])
                        break
        if fi < 0:
            reason[k] = NOFILL
            continue
        fill_i[k] = fi
        fill_px[k] = fp
        st = stop[k] if not np.isnan(stop[k]) else fp - s * stop_dist[k]
        tg = target[k] if not np.isnan(target[k]) else (
            fp + s * target_dist[k] if not np.isnan(target_dist[k]) else np.nan)
        init_stop[k] = st
        # stop on the wrong side of the fill (gap through it) -> out at once at the opposite quote
        if (s > 0 and st >= fp) or (s < 0 and st <= fp):
            x_i[k] = fi
            x_px[k] = bo[fi] * (1 - slip) if s > 0 else ao[fi] * (1 + slip)
            reason[k] = GAP
            last_exit = fi
            continue
        cur = st
        best = fp
        hi_ex = 0.0
        lo_ex = 0.0
        moved = False
        xe = exit_i[k]
        done = False
        i = fi
        while i < N:
            if xe >= 0 and i >= xe and i > fi:
                x_i[k] = i
                x_px[k] = bo[i] * (1 - slip_m) if s > 0 else ao[i] * (1 + slip_m)
                reason[k] = TIME
                done = True
                break
            first = i == fi
            if s > 0:
                hit_stop = bl[i] <= cur
                hit_tgt = (not np.isnan(tg)) and bh[i] >= tg
                if first and et == 1 and hit_tgt and not (ao[i] < level[k]):
                    hit_tgt = False
                if first and et == 2:
                    hit_tgt = False
                if hit_stop:
                    px = cur if first else min(cur, bo[i])
                    x_i[k] = i
                    x_px[k] = px * (1 - slip)
                    reason[k] = TRAIL if moved else STOP
                    done = True
                    break
                if hit_tgt:
                    x_i[k] = i
                    x_px[k] = tg if first else max(tg, bo[i])
                    reason[k] = TARGET
                    done = True
                    break
                hi_ex = max(hi_ex, bh[i] - fp)
                lo_ex = min(lo_ex, bl[i] - fp)
                if bh[i] > best:
                    best = bh[i]
                if not np.isnan(trail[k]) and best - trail[k] > cur:
                    cur = best - trail[k]
                    moved = True
                if not np.isnan(be[k]) and best - fp >= be[k] and fp > cur:
                    cur = fp
                    moved = True
            else:
                hit_stop = ah[i] >= cur
                hit_tgt = (not np.isnan(tg)) and al[i] <= tg
                if first and et == 1 and hit_tgt and not (bo[i] > level[k]):
                    hit_tgt = False
                if first and et == 2:
                    hit_tgt = False
                if hit_stop:
                    px = cur if first else max(cur, ao[i])
                    x_i[k] = i
                    x_px[k] = px * (1 + slip)
                    reason[k] = TRAIL if moved else STOP
                    done = True
                    break
                if hit_tgt:
                    x_i[k] = i
                    x_px[k] = tg if first else min(tg, ao[i])
                    reason[k] = TARGET
                    done = True
                    break
                hi_ex = max(hi_ex, fp - al[i])
                lo_ex = min(lo_ex, fp - ah[i])
                if al[i] < best:
                    best = al[i]
                if not np.isnan(trail[k]) and best + trail[k] < cur:
                    cur = best + trail[k]
                    moved = True
                if not np.isnan(be[k]) and fp - best >= be[k] and fp < cur:
                    cur = fp
                    moved = True
            i += 1
        if not done:
            x_i[k] = N - 1
            x_px[k] = bc[N - 1] if s > 0 else ac[N - 1]
            reason[k] = EOD
        mfe[k] = hi_ex
        mae[k] = lo_ex
        last_exit = x_i[k]


_DEFAULTS = {"etype": 0, "level": np.nan, "expiry_i": -1, "stop": np.nan, "stop_dist": np.nan,
             "target": np.nan, "target_dist": np.nan, "exit_i": -1, "trail": np.nan, "be": np.nan}


def apply_spread_mult(m1, k):
    """Return a copy of `m1` whose bid/ask spread is scaled by k around the mid (same transform
    simulate() applies for Costs.spread_mult). Build orders on THIS frame when a strategy
    pre-resolves fills from the quotes, then simulate it with spread_mult=1."""
    if k == 1.0:
        return m1
    half = (m1["ac"] - m1["bc"]) * (k - 1) / 2
    out = m1.copy()
    for c in ("bo", "bh", "bl", "bc"):
        out[c] = m1[c] - half
    for c in ("ao", "ah", "al", "ac"):
        out[c] = m1[c] + half
    return out


def simulate_rebuilt(m1, make_orders, params, sym="xauusd", costs=None, no_overlap=True):
    """Scenario-consistent simulation: orders are rebuilt on the spread-scaled quotes, so
    strategies that pre-resolve first touches see the same quotes as the fill engine."""
    c = costs or COSTS.get(sym, Costs())
    mk = apply_spread_mult(m1, c.spread_mult)
    from dataclasses import replace as _replace
    return simulate(mk, make_orders(mk, **params), sym=sym, costs=_replace(c, spread_mult=1.0),
                    no_overlap=no_overlap)


def simulate(m1, orders, sym="xauusd", costs=None, no_overlap=True):
    """Run `orders` (DataFrame, see module doc) on M1 frame `m1`.
    Returns a DataFrame of filled trades with pnl in price units per 1 unit, R multiple, etc.
    no_overlap=True: an order activating while a previous trade is open is skipped
    (one position at a time, like a simple EA)."""
    c = costs or COSTS.get(sym, Costs())
    orders = orders.reset_index(drop=True)
    o = orders.copy()
    for k, v in _DEFAULTS.items():
        if k not in o:
            o[k] = v
    if ((o["etype"] > 0) & (o["expiry_i"] < 0)).any():
        raise ValueError("pending orders (etype 1/2) need expiry_i")
    if o["stop"].isna().any() and o.loc[o["stop"].isna(), "stop_dist"].isna().any():
        raise ValueError("every order needs a stop or stop_dist")
    o = o.sort_values("entry_i", kind="stable")
    n = len(o)
    bo, bh, bl, bc = (m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc"))
    ao, ah, al, ac = (m1[k].to_numpy(np.float64) for k in ("ao", "ah", "al", "ac"))
    if c.spread_mult != 1.0:
        half = (m1["ac"].to_numpy() - m1["bc"].to_numpy()) * (c.spread_mult - 1) / 2
        bo, bh, bl, bc = bo - half, bh - half, bl - half, bc - half
        ao, ah, al, ac = ao + half, ah + half, al + half, ac + half
    fill_i = np.full(n, -1, np.int64)
    x_i = np.full(n, -1, np.int64)
    fill_px, x_px, init_stop = (np.full(n, np.nan) for _ in range(3))
    mfe, mae = np.zeros(n), np.zeros(n)
    reason = np.full(n, -1, np.int64)
    _run(bo, bh, bl, bc, ao, ah, al, ac,
         o["entry_i"].to_numpy(np.int64), o["side"].to_numpy(np.int64), o["etype"].to_numpy(np.int64),
         o["level"].to_numpy(np.float64), o["expiry_i"].to_numpy(np.int64), o["stop"].to_numpy(np.float64),
         o["stop_dist"].to_numpy(np.float64), o["target"].to_numpy(np.float64),
         o["target_dist"].to_numpy(np.float64), o["exit_i"].to_numpy(np.int64),
         o["trail"].to_numpy(np.float64), o["be"].to_numpy(np.float64),
         c.slip_bps * 1e-4, (c.slip_mkt_bps if c.slip_mkt_bps >= 0 else c.slip_bps) * 1e-4, bool(no_overlap),
         fill_i, fill_px, x_i, x_px, reason, init_stop, mfe, mae)
    ok = fill_i >= 0
    idx = m1.index
    t = pd.DataFrame({
        "side": o["side"].to_numpy()[ok],
        "entry_time": idx[fill_i[ok]],
        "exit_time": idx[x_i[ok]] + pd.Timedelta(minutes=1) * (reason[ok] != TIME),
        "entry": fill_px[ok], "exit": x_px[ok], "stop": init_stop[ok],
        "reason": pd.Series(reason[ok]).map(REASONS).to_numpy(),
        "mfe": mfe[ok], "mae": mae[ok],
    }, index=o.index[ok])
    reserved = set(t.columns) | {"swap", "commission", "pnl", "risk", "R", "ret", "hold_min"}
    for extra in [col for col in orders.columns if col not in _DEFAULTS and col not in ("entry_i", "side")]:
        # an order column that has the name of an engine output is carried as "o_<name>" (never overwrites)
        t[("o_" + extra) if extra in reserved else extra] = o.loc[t.index, extra].to_numpy()
    gross = t.side * (t.exit - t.entry)
    # swap: rollovers at 17:00 NY between entry and exit trading days, triple on c.swap_triple (Wednesday by default)
    d0 = trading_day(t.entry_time).values.astype("datetime64[D]")
    d1 = trading_day(t.exit_time - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    nights = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask=c.swap_triple)
    rate = np.where(t.side > 0, c.swap_long, c.swap_short)
    t["swap"] = t.entry * rate / 360.0 * nights
    t["commission"] = c.commission
    t["pnl"] = gross - t["swap"] - t["commission"]
    t["risk"] = (t.entry - t.stop).abs()
    t["R"] = t.pnl / t.risk.where(t.risk > 0)
    t["ret"] = t.pnl / t.entry
    t["hold_min"] = (t.exit_time - t.entry_time).dt.total_seconds() / 60
    n_skip = int((reason == SKIP).sum())
    n_nofill = int((reason == NOFILL).sum())
    t.attrs.update(skipped=n_skip, nofill=n_nofill, orders=n, sym=sym)
    return t.sort_values("entry_time")
