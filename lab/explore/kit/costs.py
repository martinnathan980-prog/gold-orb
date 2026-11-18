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


def spec(key):
    if key not in SPEC:
        raise CostError(f"no FP cost entry for '{key}' in lab/r2/fp_costs.json: this market cannot be judged net of costs")
    return SPEC[key]


def how_ny(times):
    """Hour of the week on the New York clock (Mon 00:00 = 0 ... Sun 23:00 = 167)."""
    ny = pd.DatetimeIndex(times).tz_convert(NY)
    return np.asarray(ny.dayofweek * 24 + ny.hour, dtype=np.int64)


def shape(key, times, at="open"):
    """Hour-of-week spread shape at a bar's open (hh:00 minute) or close (hh:59 minute: the last bar before a closure,
    e.g. the Friday 16:59 New York close, is much wider than its open)."""
    spec(key)
    tab = SHAPE if at == "open" else SHAPE_CLOSE
    if key not in tab:
        raise CostError(f"no spread shape for {key} in kit/spread_shape.json")
    return tab[key][how_ny(times)]


def base_spread(key, price):
    """Spread (price units) at the given price(s) before the intraday shape."""
    s = spec(key)
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
    s = spec(key)
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
