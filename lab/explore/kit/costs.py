"""FP Markets Raw costs with the lab's conventions. Every convention names the lab file it copies.

- Values: lab/r2/fp_costs.json (read at import; a market without an entry raises CostError).
- Spread (lab/build_fp_frames.py, lab/COSTS_FP.md): today's FP spread, Raw commission folded in, turned into basis
  points at `spread_ref_price` and applied to the trade's price, times Dukascopy's intraday spread shape. The shape is
  kit/spread_shape.json: for each market, 168 numbers (New York weekday*24 + hour) = in-sample mean of
  clip(spread at the hh:00 minute / median spread of its 17:00-NY trading day, 0.7, 6) from the lab's own Dukascopy M1
  bid/ask (the same clipped ratio build_fp_frames.py applies minute by minute, averaged per hour of the week because the
  kit works on hourly bars; its mean equals the expected shape factor of an order at that hour's open).
  Markets WITHOUT spread_ref_price in the file (the FX pairs and silver): build_fp_frames.py used the mean price of the
  last 60 trading days of its data (late 2025) as reference; the runs cannot read that, so the kit uses an approximate
  late-2025 price (REF_FALLBACK below, round numbers; silver 55.5 from lab/COSTS_FP.md) in the same way: the spread in
  bp of that price, applied to the trade's price. This is the lab's forward-looking model for every market
  (fp_costs.json '_model': today's cost in basis points of price, applied to the whole history). Lead's ruling of
  2026-11-18: the first version of the kit charged max(absolute amount, bp), which made silver 2.3 times and the yen
  pairs 1.2-1.3 times dearer in sample than the lab's own frames; the rule that judged the ten is the one kept.
- Slippage (lab/goldlab/sim.py, lab/goldlab/r2.py costs()): slip_mkt_bps per side on market fills (entry at a bar open,
  time exits), slip_stop_bps on stop exits (also when the bar opens beyond the stop), none on targets (limit fills).
- Swaps (lab/goldlab/sim.py simulate()): one night per 17:00 New York rollover between the trading day of the entry and
  the trading day of (exit - 1 s), counted on business days (numpy busday_count), the swap_triple weekday counting 3;
  cost = annual rate / 360 x entry price x nights, rate of the side held; credits are ignored (rates are >= 0 in the file).
- Stress (lab/COSTS_FP.md, lab/goldlab/r2.py run(mode='stress')): spread x 1.5 and slippage x 1.5; swaps unchanged.
- Gross (lab/goldlab/r2.py run(mode='gross')): spread 0 (mid prices), slippage 0, swap 0.
"""
import json
import os

import numpy as np
import pandas as pd

KIT = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(KIT, "..", ".."))
NY = "America/New_York"
STRESS = 1.5
SCENARIOS = {"gross": (0.0, 0.0, False), "net": (1.0, 1.0, True), "stress": (STRESS, STRESS, True)}  # spread, slip, swap
REF_FALLBACK = {"eurusd": 1.16, "gbpusd": 1.33, "usdjpy": 152.0, "audusd": 0.65, "usdcad": 1.39, "usdchf": 0.80,
                "nzdusd": 0.57, "eurjpy": 176.0, "xagusd": 55.5}


class CostError(KeyError):
    pass


def _load():
    p = os.environ.get("EXPLORE_FP_COSTS", os.path.join(LAB, "r2", "fp_costs.json"))
    return {k: v for k, v in json.load(open(p)).items() if not k.startswith("_")}


SPEC = _load()
_SJ = json.load(open(os.path.join(KIT, "spread_shape.json")))
SHAPE = {k: np.asarray(v, float) for k, v in _SJ["shape"].items()}
SHAPE_CLOSE = {k: np.asarray(v, float) for k, v in _SJ.get("shape_close", _SJ["shape"]).items()}


PAIRS = {}          # hedged pairs registered by sim.pair_book (kept apart from SPEC: SPEC lists the FP markets only)


def spec(key):
    if key in SPEC:
        return SPEC[key]
    if key in PAIRS:
        return PAIRS[key]
    raise CostError(f"no FP cost entry for '{key}' in lab/r2/fp_costs.json: this market cannot be judged net of costs")


def register_pair(name, key_a, key_b, kind="ratio"):
    """Register a hedged pair as ONE market (lead's ruling of 2026-11-18, CHARTER 'Rulings'), so that spec(name) works
    in sim, stats and judge. kind 'ratio': price a / b, long the pair = long a and short b; 'product': price a x b (a
    cross built from two dollar pairs quoted opposite ways, EURCHF = EURUSD x USDCHF), long the pair = long a and long
    b. Two legs of equal notional at entry (scout/ideas.md conventions), each leg paying its own FP costs: the pair's
    spec carries the legs and the sum of their slippages (per unit of ONE leg's notional, the unit of a pair's result);
    spread and swap stay per leg (sim.PairBook). The legs must share the triple-swap weekday, else CostError (one
    night count for both legs). Registering the same name again with the same legs is harmless; other legs raise."""
    if kind not in ("ratio", "product"):
        raise ValueError("kind is 'ratio' or 'product'")
    if name in SPEC:
        raise CostError(f"'{name}' is an FP market of fp_costs.json: give the pair its own name (e.g. 'eurusd/gbpusd')")
    if key_a == key_b or key_a in PAIRS or key_b in PAIRS:
        raise ValueError("a pair has two different legs, each an FP market (not a pair)")
    a, b = spec(key_a), spec(key_b)
    ta, tb = a.get("swap_triple", "Wed"), b.get("swap_triple", "Wed")
    if ta != tb:
        raise CostError(f"pair {name}: legs {key_a} (triple swap {ta}) and {key_b} ({tb}) do not share the triple-swap "
                        "weekday: one night count cannot serve both legs")
    new = {"pair": {"legs": (key_a, key_b), "kind": kind, "sides": (1, -1 if kind == "ratio" else 1)},
           "swap_triple": ta, "slip_mkt_bps": a["slip_mkt_bps"] + b["slip_mkt_bps"],
           "slip_stop_bps": a["slip_stop_bps"] + b["slip_stop_bps"],
           "weekdays_only": bool(a.get("weekdays_only") or b.get("weekdays_only"))}
    if name in PAIRS and PAIRS[name]["pair"] != new["pair"]:
        raise ValueError(f"pair {name} is already registered with legs {PAIRS[name]['pair']}")
    PAIRS[name] = new
    return new


def _not_pair(key):
    s = spec(key)
    if "pair" in s:
        raise CostError(f"{key} is a hedged pair: its spread and swaps are per leg (sim.PairBook, costs.pair_round_trip)")
    return s


def how_ny(times):
    """Hour of the week on the New York clock (Mon 00:00 = 0 ... Sun 23:00 = 167)."""
    ny = pd.DatetimeIndex(times).tz_convert(NY)
    return np.asarray(ny.dayofweek * 24 + ny.hour, dtype=np.int64)


def shape(key, times, at="open"):
    """Hour-of-week spread shape at a bar's open (hh:00 minute) or close (hh:59 minute: the last bar before a closure,
    e.g. the Friday 16:59 New York close, is much wider than its open)."""
    _not_pair(key)
    tab = SHAPE if at == "open" else SHAPE_CLOSE
    if key not in tab:
        raise CostError(f"no spread shape for {key} in kit/spread_shape.json")
    return tab[key][how_ny(times)]


def base_spread(key, price):
    """Spread (price units) at the given price(s) before the intraday shape."""
    s = _not_pair(key)
    price = np.asarray(price, float)
    if s.get("spread_ref_price"):
        return s["spread"] / s["spread_ref_price"] * price
    if key not in REF_FALLBACK:
        raise CostError(f"{key}: no spread_ref_price and no fallback reference price")
    return s["spread"] / REF_FALLBACK[key] * price


def spread(key, price, times=None, mult=1.0, at="open"):
    """Modelled FP spread in price units at `price`, with the hour-of-week shape if `times` (bar open times) is given
    (at='open' for orders at the bar's open, 'close' for an exit at its close), times `mult`."""
    b = base_spread(key, price)
    if times is not None:
        b = b * shape(key, times, at)
    return b * mult


def slip(key, kind, mult=1.0):
    """Slippage as a fraction of price, per side: kind 'mkt' (market/time), 'stop', 'target' (0)."""
    s = spec(key)
    if kind == "target":
        return 0.0
    return {"mkt": s["slip_mkt_bps"], "stop": s["slip_stop_bps"]}[kind] * 1e-4 * mult


def trading_day(ts):
    ny = pd.DatetimeIndex(ts).tz_convert(NY)
    return (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize()


def swap_nights(entry_time, exit_time, triple="Wed"):
    """Rollovers (17:00 New York) held, the triple weekday counting 3 (lab/goldlab/sim.py)."""
    d0 = trading_day(entry_time).values.astype("datetime64[D]")
    d1 = trading_day(pd.DatetimeIndex(exit_time) - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    return np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask=triple)


def held_tdays(entry_time, exit_time):
    """Trading days held = weekday rollovers crossed (no triple)."""
    d0 = trading_day(entry_time).values.astype("datetime64[D]")
    d1 = trading_day(pd.DatetimeIndex(exit_time) - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    return np.busday_count(d0, d1)


def swap(key, side, entry_price, entry_time, exit_time):
    """Swap cost in price units per unit (>= 0)."""
    s = _not_pair(key)
    side = np.asarray(side)
    rate = np.where(side > 0, s["swap_long"], s["swap_short"])
    return rate / 360.0 * np.asarray(entry_price, float) * swap_nights(entry_time, exit_time, s.get("swap_triple", "Wed"))


def round_trip(key, side, mid_in, mid_out, t_in, t_out, scenario="net", exit_kind="mkt", exit_at="open"):
    """Hand-checkable cost of one trade entered at market at mid_in (time t_in) and left at mid_out (t_out) by a market
    order ('mkt') or a stop ('stop'): returns dict of the cost parts in price units and the total in bp of mid_in."""
    k_spr, k_slip, with_swap = SCENARIOS[scenario]
    s_in = float(spread(key, mid_in, pd.DatetimeIndex([t_in]), k_spr)[0])
    s_out = float(spread(key, mid_out, pd.DatetimeIndex([pd.Timestamp(t_out).floor("h")]), k_spr, exit_at)[0])
    if side > 0:
        fill = (mid_in + s_in / 2) * (1 + slip(key, "mkt", k_slip))
        out = (mid_out - s_out / 2) * (1 - slip(key, exit_kind, k_slip))
    else:
        fill = (mid_in - s_in / 2) * (1 - slip(key, "mkt", k_slip))
        out = (mid_out + s_out / 2) * (1 + slip(key, exit_kind, k_slip))
    sw = float(swap(key, [side], [fill], pd.DatetimeIndex([t_in]), pd.DatetimeIndex([t_out]))[0]) if with_swap else 0.0
    gross = side * (mid_out - mid_in)
    net = side * (out - fill) - sw
    return {"spread_in": s_in, "spread_out": s_out, "fill": fill, "exit": out, "swap": sw,
            "cost": gross - net, "cost_bp": (gross - net) / mid_in * 1e4}


def pair_round_trip(name, side, bid_in, bid_out, t_in, t_out, scenario="net", exit_kind="mkt", exit_at="open"):
    """Hand-checkable cost of one hedged-pair trade (the pair registered by sim.pair_book) entered at market at the
    open of the bar starting t_in and left at t_out by a market order ('mkt') or a stop ('stop'), at the bar's open
    ('open') or its close ('close': close-of-bar spread shape). bid_in / bid_out: the legs' BID prices (a, b) of
    bars of price_is 'bid' (Dukascopy). Each leg pays its own spread (bp of its reference price x its hour-of-week
    shape), its own slippage and the swap of the side it holds (long leg swap_long, short leg swap_short) over the pair's
    nights (shared triple weekday). Result per unit of ONE leg's notional = sum over legs of leg side x (exit / fill - 1)
    - swaps (sim.PairBook: the exact two-leg result). Returns the legs' fills and exits, the swap and the cost in bp of
    one leg's notional (gross result at the legs' mids minus the net result)."""
    s = spec(name)
    if "pair" not in s:
        raise CostError(f"{name} is not a registered pair (sim.pair_book registers it)")
    legs, sides = s["pair"]["legs"], s["pair"]["sides"]
    k_spr, k_slip, with_swap = SCENARIOS[scenario]
    ti, to = pd.DatetimeIndex([t_in]), pd.DatetimeIndex([pd.Timestamp(t_out).floor("h")])
    out = {"fill": [], "exit": [], "mid_in": [], "mid_out": []}
    net = gross = 0.0
    nights = int(swap_nights(pd.DatetimeIndex([t_in]), pd.DatetimeIndex([t_out]), s["swap_triple"])[0])
    sw = 0.0
    for key, ls, bi, bo in zip(legs, sides, bid_in, bid_out):
        ls = ls * side
        s_in = float(spread(key, bi, ti)[0])            # base spread at the bid (as kit.sim.Book at a bid bar's open)
        s_out = float(spread(key, bo, to, at=exit_at)[0])
        m_in, m_out = bi + s_in / 2, bo + s_out / 2
        h_in, h_out = k_spr * s_in / 2, k_spr * s_out / 2
        fill = (m_in + h_in) * (1 + slip(key, "mkt", k_slip)) if ls > 0 else (m_in - h_in) * (1 - slip(key, "mkt", k_slip))
        ex = (m_out - h_out) * (1 - slip(key, exit_kind, k_slip)) if ls > 0 else (m_out + h_out) * (1 + slip(key, exit_kind, k_slip))
        net += ls * (ex / fill - 1)
        gross += ls * (m_out / m_in - 1)
        if with_swap:
            sp = spec(key)
            sw += (sp["swap_long"] if ls > 0 else sp["swap_short"]) / 360.0 * nights
        out["fill"].append(fill); out["exit"].append(ex); out["mid_in"].append(m_in); out["mid_out"].append(m_out)
    net -= sw
    out.update(swap=sw, nights=nights, net=net, gross=gross, cost_bp=(gross - net) * 1e4)
    return out
