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
- Kit v2.1 markets (kit/extra_costs.json, read beside fp_costs.json, which is never edited): oil and 40 US share CFDs,
  every figure PROVISIONAL (is_provisional; judge.verdict writes 'PROVISIONAL COSTS') with its source. Extra fields:
  spread_bps (spread in bp of the trade's price; shares: the in-sample median QUOTED spread of the data, the lab's share
  convention, lab/prep_round3.py) times the hour-of-week shape of kit/extra_shape.json; commission_per_unit (price units
  per unit per side: 0.02 USD per share, fp_costs.json '_stocks') added on each side on top of the half spread, inside
  the quotes before slippage as the lab's share frames add it to the quotes (prep_round3.py stock()), x1.5 in the stress
  (the lab's stress widens the frame's spread, commission included: lab/r2/tracks/stocks/transfer.py) and 0 in gross; it
  is split-adjusted (data.load_bars back-adjusts the share bars; sim.Book scales the commission by data.split_factor: one
  adjusted unit before a 4:1 split is a quarter of a real share, so it pays a quarter of the commission, as
  prep_round3.py's frames x factor). The
  minimum commission per order (2 USD per side) was first reported only; it is MODELLED since the fix below (V21-2).
- Kit v2.1 fix (2026-11-18, verifier V21-1..8):
  * Shares: commission_per_unit 0.03 USD in net (0.045 stress, 0 gross); the 2 USD minimum per side IS MODELLED:
    commission per unit = max(commission_per_unit x adj, min_commission_per_side x price / trade_notional(key)), with
    the stake notional of extra_costs.json '_stake' (5,000 EUR / 6 positions x leverage x 1.15 USD/EUR = 4,791.67 USD
    at 1:5): below about 72 USD a share the per-share rate binds, above it the minimum (4.17 bp per side).
  * Shares: spread level by New York calendar year (spread_bps_by_year), spread_bps for the years not listed. Each
    level is CALIBRATED so that the kit's mean spread (level x shape) over the year's bar-open minutes equals the mean
    quoted spread of the data at those minutes (the first step was the mean of the daily median quoted spread).
- Kit v2.1 fix 2 (2026-11-18, verifier KF-1..KF-10):
  * Shares: TWO levels per year (KF-5): spread_bps_by_year_h09 for an order at the open of the 09:00-labelled bar (the
    09:30 first minute) and spread_bps_by_year for every other bar open and every bar close; each calibrated on its own
    minutes (09:30, or hh:00 10-15). spread_bps_h09 / spread_bps for the years not listed.
  * Shares: dividend_credit_long = 0.70 (KF-4: a long is credited 70 % of the dividend, the US withholding of 30 %
    without a treaty, the pessimistic side of the usual 70-100 % CFD credit; to read in MetaTrader); judge.verdict
    reports the long result at credits 0 and 1 as well.
  * Oil: the roll ratios are LISTED (outside settlements, KF-1); round_trip's adj defaults to data.price_factor for a
    market with rolls or splits (KF-8); pair_round_trip takes adj_out per leg (KF-8).
  * The exit-side minimum commission is charged at the EXIT price (min x P_exit / N), while with the units fixed at
    entry it is min x P_entry / N: about 0.4 bp more on a trade whose price rose 10 %, as much less when it fell (KF-9,
    left as it is: README limits).
  * Shares: dividends: a SHORT open at an ex-date's first bar pays dividend / previous close x its fill (in swap();
    a long is credited dividend_credit_long x that, 0 = credits ignored as for swaps).
  * Oil: spread_abs = a constant 0.05 USD per barrel (x the roll adjustment of the bar, data.price_factor), not bp.
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


def _load_extra():
    """kit/extra_costs.json (kit v2.1): markets judged on PROVISIONAL costs. Kept apart from SPEC (SPEC = the FP markets
    of fp_costs.json); a key of both, or an entry without provisional/source, raises at import."""
    p = os.environ.get("EXPLORE_EXTRA_COSTS", os.path.join(KIT, "extra_costs.json"))
    if not os.path.isfile(p):
        return {}
    out = {k: v for k, v in json.load(open(p)).items() if not k.startswith("_")}
    for k, v in out.items():
        if k in SPEC:
            raise CostError(f"{k} is in both fp_costs.json and extra_costs.json")
        if "provisional" not in v or not v.get("source"):
            raise CostError(f"extra_costs.json {k}: every entry says provisional and gives its source")
    return out


SPEC = _load()
EXTRA = _load_extra()
_SJ = json.load(open(os.path.join(KIT, "spread_shape.json")))
SHAPE = {k: np.asarray(v, float) for k, v in _SJ["shape"].items()}
SHAPE_CLOSE = {k: np.asarray(v, float) for k, v in _SJ.get("shape_close", _SJ["shape"]).items()}
_XJ = json.load(open(os.path.join(KIT, "extra_shape.json"))) if os.path.isfile(os.path.join(KIT, "extra_shape.json")) else \
    {"shape": {}, "shape_close": {}}
for _k in EXTRA:
    if _k in _XJ["shape"] and _k not in SHAPE:
        SHAPE[_k] = np.asarray(_XJ["shape"][_k], float)
        SHAPE_CLOSE[_k] = np.asarray(_XJ.get("shape_close", _XJ["shape"])[_k], float)


PAIRS = {}          # hedged pairs registered by sim.pair_book (kept apart from SPEC: SPEC lists the FP markets only)


def spec(key):
    if key in SPEC:
        return SPEC[key]
    if key in EXTRA:
        return EXTRA[key]
    if key in PAIRS:
        return PAIRS[key]
    raise CostError(f"no FP cost entry for '{key}' in lab/r2/fp_costs.json or kit/extra_costs.json: this market cannot "
                    "be judged net of costs")


def is_provisional(key):
    """True for a market whose costs are PROVISIONAL (kit/extra_costs.json), or a pair with such a leg."""
    return bool(spec(key).get("provisional", False))


def min_day_bars(key):
    """Bars a 17:00-NY trading day needs to count in D20: the entry's min_day_bars, 10 by default (shares: 7, a full
    09:30-16:00 session of hourly bars)."""
    return int(spec(key).get("min_day_bars", 10))


def _stake():
    p = os.environ.get("EXPLORE_EXTRA_COSTS", os.path.join(KIT, "extra_costs.json"))
    st = json.load(open(p)).get("_stake", {}) if os.path.isfile(p) else {}
    return {"account_eur": float(st.get("account_eur", 5000.0)), "positions": int(st.get("positions", 6)),
            "usd_per_eur": float(st.get("usd_per_eur", 1.15))}


STAKE = _stake()


def trade_notional(key, account_eur=None):
    """Notional of one trade (quote currency, USD for the kit v2.1 markets) at which the minimum commission per order is
    modelled (verifier V21-2): the charter's account (5,000 EUR by default, extra_costs.json '_stake') split over its 6
    positions, at the market's leverage: 5,000 / 6 x 5 x 1.15 = 4,791.67 USD for a share at 1:5."""
    s = spec(key)
    acc = STAKE["account_eur"] if account_eur is None else float(account_eur)
    return acc / STAKE["positions"] * float(s.get("leverage", 1)) * STAKE["usd_per_eur"]


def commission(key, adj=1.0, price=None):
    """Commission per unit per side in price units (0 for every market of fp_costs.json, whose commission is folded
    into the spread): commission_per_unit x adj (adj = the bars' split adjustment, 1 without a split); with `price` (the
    order's price, in the bars' adjusted units) and a min_commission_per_side, the minimum per order is modelled at the
    stake notional N = trade_notional(key): max(commission_per_unit x adj, min_commission_per_side x price / N) (kit v2.1
    fix, V21-2: N / price units are traded, so the minimum costs min / N of the price per unit)."""
    s = _not_pair(key)
    c = float(s.get("commission_per_unit", 0.0))
    out = c * np.asarray(adj, float) if c else (0.0 * np.asarray(adj, float))
    mc = float(s.get("min_commission_per_side", 0.0))
    if c and mc and price is not None:
        out = np.maximum(out, mc * np.asarray(price, float) / trade_notional(key))
    return out


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
    if name in SPEC or name in EXTRA:
        raise CostError(f"'{name}' is a market of fp_costs.json or extra_costs.json: give the pair its own name (e.g. "
                        "'eurusd/gbpusd')")
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
    if a.get("provisional") or b.get("provisional"):
        new["provisional"] = True
    if "min_day_bars" in a or "min_day_bars" in b:            # the pair's bars are the hours both legs have
        new["min_day_bars"] = min(int(a.get("min_day_bars", 10)), int(b.get("min_day_bars", 10)))
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


def _year_bps(s, times, at="open"):
    """spread_bps of each time: spread_bps_by_year of its New York calendar year, else spread_bps (kit v2.1 fix, V21-4);
    for an order at the OPEN of a share's 09:00-labelled bar (its 09:30 first minute), spread_bps_by_year_h09 / spread_bps_h09
    (kit v2.1 fix 2, KF-5). A scalar without times or without a table, else one value per time."""
    by = s.get("spread_bps_by_year")
    if not by or times is None:
        return float(s["spread_bps"])
    nyt = pd.DatetimeIndex(times).tz_convert(NY)
    yr = nyt.year.to_numpy()
    out = np.full(len(yr), float(s["spread_bps"]))
    for y, v in by.items():
        out[yr == int(y)] = float(v)
    b9 = s.get("spread_bps_by_year_h09")
    if b9 and at == "open":
        h9 = nyt.hour.to_numpy() == 9
        if h9.any():
            o9 = np.full(len(yr), float(s.get("spread_bps_h09", s["spread_bps"])))
            for y, v in b9.items():
                o9[yr == int(y)] = float(v)
            out = np.where(h9, o9, out)
    return out


def base_spread(key, price, times=None, adj=1.0, at="open"):
    """Spread (price units) at the given price(s) before the intraday shape. times (bar open times) select a share's
    level of the year (and of the 09 bar's open, at='open'); adj = the bars' price adjustment (data.price_factor: an oil
    roll), used by spread_abs only."""
    s = _not_pair(key)
    price = np.asarray(price, float)
    if "spread_abs" in s:                                   # kit v2.1 fix (V21-3): oil, a constant amount in USD
        return s["spread_abs"] * np.asarray(adj, float) * np.ones_like(price)
    if "spread_bps" in s:                                   # kit v2.1 markets: bp of the trade's price
        return np.asarray(_year_bps(s, times, at)) * 1e-4 * price
    if s.get("spread_ref_price"):
        return s["spread"] / s["spread_ref_price"] * price
    if key not in REF_FALLBACK:
        raise CostError(f"{key}: no spread_ref_price and no fallback reference price")
    return s["spread"] / REF_FALLBACK[key] * price


def spread(key, price, times=None, mult=1.0, at="open", adj=1.0):
    """Modelled FP spread in price units at `price`, with the hour-of-week shape if `times` (bar open times) is given
    (at='open' for orders at the bar's open, 'close' for an exit at its close), times `mult`; adj: see base_spread."""
    b = base_spread(key, price, times, adj, at)
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


_DIV = {}


def _div_table(key):
    """(ex-date first-bar open times as int64 ns UTC: 09:00 New York label of the ex-date, fractions, checked-to end)."""
    if key not in _DIV:
        s = spec(key)
        d = s.get("dividends") or {}
        t = pd.DatetimeIndex([pd.Timestamp(x) + pd.Timedelta(hours=9) for x in d]).tz_localize(NY).tz_convert("UTC")
        chk = (pd.Timestamp(s.get("dividends_checked_to", "1900-01-01")) + pd.Timedelta(days=1)).tz_localize(NY)
        _DIV[key] = (t.as_unit("ns").asi8, np.asarray(list(d.values()), float), chk.tz_convert("UTC"))
    return _DIV[key]


def dividends(key, side, entry_price, entry_time, exit_time, credit_long=None):
    """Dividend cost in price units per unit (kit v2.1 fix, V21-8), for a share with a 'dividends' list
    {ex-date: dividend / previous close}: a position open at the ex-date's first bar (entry before the 09:00-labelled bar
    of the ex-date, the 09:30 open, and exit at or after it: the exit price is then ex-dividend) pays, if SHORT, the
    sum of those fractions x its entry price; a LONG is credited dividend_credit_long x that (0 in the file: credits
    ignored, as for swaps; 0.70 since the kit v2.1 fix 2, KF-4; credit_long overrides it, for judge's sensitivity
    report). 0 for every other market. A trade whose exit is past dividends_checked_to raises CostError (the later
    dividends are not listed)."""
    s = _not_pair(key)
    side = np.atleast_1d(np.asarray(side))
    if "dividends" not in s:
        return np.zeros(len(side))
    t, fr, chk = _div_table(key)
    et = pd.DatetimeIndex(entry_time).tz_convert("UTC").as_unit("ns").asi8
    xt = pd.DatetimeIndex(exit_time).tz_convert("UTC").as_unit("ns").asi8
    if len(xt) and xt.max() > chk.value:
        raise CostError(f"{key}: its dividends are listed to {s.get('dividends_checked_to')} only; a trade to "
                        f"{pd.Timestamp(xt.max(), tz='UTC')} needs the later ones in kit/extra_costs.json first")
    cs = np.r_[0.0, np.cumsum(fr)]
    i0 = np.searchsorted(t, et, side="right")                # ex-opens strictly after the entry
    i1 = np.searchsorted(t, xt, side="right")                # ex-opens at or before the exit
    tot = np.where(i1 > i0, cs[np.maximum(i1, i0)] - cs[i0], 0.0)
    cl = float(s.get("dividend_credit_long", 0.0)) if credit_long is None else float(credit_long)
    k = np.where(side > 0, -cl, 1.0)
    return k * tot * np.asarray(entry_price, float)


def swap(key, side, entry_price, entry_time, exit_time):
    """Swap cost in price units per unit (>= 0), plus a share's dividends (dividends())."""
    s = _not_pair(key)
    side = np.asarray(side)
    rate = np.where(side > 0, s["swap_long"], s["swap_short"])
    out = rate / 360.0 * np.asarray(entry_price, float) * swap_nights(entry_time, exit_time, s.get("swap_triple", "Wed"))
    if "dividends" in s:
        out = out + dividends(key, side, entry_price, entry_time, exit_time)
    return out


def _default_adj(key, t):
    """data.price_factor at time t for a market with rolls or splits (kit v2.1 fix 2, KF-8), else 1.0."""
    s = spec(key)
    if "rolls" not in s and "splits" not in s:
        return 1.0
    from . import data as _D                                    # lazy: data imports costs
    return float(_D.price_factor(key, pd.DatetimeIndex([pd.Timestamp(t)]))[0])


def round_trip(key, side, mid_in, mid_out, t_in, t_out, scenario="net", exit_kind="mkt", exit_at="open", adj=None,
               adj_out=None):
    """Hand-checkable cost of one trade entered at market at mid_in (time t_in) and left at mid_out (t_out) by a market
    order ('mkt') or a stop ('stop'): returns dict of the cost parts in price units and the total in bp of mid_in.
    A market with commission_per_unit pays it on each side on top of the half spread, before slippage (x1.5 in the
    stress, 0 in gross; adj = the bars' price adjustment at the entry (split, oil roll), adj_out at the exit (adj by
    default). Kit v2.1 fix: the commission per side is max(per unit x adj, minimum per order x price / stake notional)
    at each side's mid (costs.commission), and the swap includes a share's dividends. Kit v2.1 fix 2 (KF-8): adj
    defaults to data.price_factor at t_in for a market with rolls or splits (1 otherwise), adj_out to the one at t_out
    when adj is not given (to adj when it is)."""
    k_spr, k_slip, with_swap = SCENARIOS[scenario]
    if adj is None:
        adj = _default_adj(key, t_in)
        adj_out = _default_adj(key, pd.Timestamp(t_out).floor("h")) if adj_out is None else adj_out
    adj_out = adj if adj_out is None else adj_out
    s_in = float(spread(key, mid_in, pd.DatetimeIndex([t_in]), k_spr, adj=adj)[0])
    s_out = float(spread(key, mid_out, pd.DatetimeIndex([pd.Timestamp(t_out).floor("h")]), k_spr, exit_at, adj=adj_out)[0])
    cm = float(commission(key, adj, mid_in)) * k_spr
    cm_out = float(commission(key, adj_out, mid_out)) * k_spr
    if side > 0:
        fill = (mid_in + s_in / 2 + cm) * (1 + slip(key, "mkt", k_slip))
        out = (mid_out - s_out / 2 - cm_out) * (1 - slip(key, exit_kind, k_slip))
    else:
        fill = (mid_in - s_in / 2 - cm) * (1 - slip(key, "mkt", k_slip))
        out = (mid_out + s_out / 2 + cm_out) * (1 + slip(key, exit_kind, k_slip))
    sw = float(swap(key, [side], [fill], pd.DatetimeIndex([t_in]), pd.DatetimeIndex([t_out]))[0]) if with_swap else 0.0
    gross = side * (mid_out - mid_in)
    net = side * (out - fill) - sw
    return {"spread_in": s_in, "spread_out": s_out, "commission_per_side": cm, "commission_out": cm_out, "fill": fill,
            "exit": out, "swap": sw,
            "cost": gross - net, "cost_bp": (gross - net) / mid_in * 1e4}


def pair_round_trip(name, side, bid_in, bid_out, t_in, t_out, scenario="net", exit_kind="mkt", exit_at="open",
                    adj=None, adj_out=None):
    """Hand-checkable cost of one hedged-pair trade (the pair registered by sim.pair_book) entered at market at the
    open of the bar starting t_in and left at t_out by a market order ('mkt') or a stop ('stop'), at the bar's open
    ('open') or its close ('close': close-of-bar spread shape). bid_in / bid_out: the legs' BID prices (a, b) of
    bars of price_is 'bid' (Dukascopy). Each leg pays its own spread (bp of its reference price x its hour-of-week
    shape), its own slippage and the swap of the side it holds (long leg swap_long, short leg swap_short) over the pair's
    nights (shared triple weekday). Result per unit of ONE leg's notional = sum over legs of leg side x (exit / fill - 1)
    - swaps (sim.PairBook: the exact two-leg result). Returns the legs' fills and exits, the swap and the cost in bp of
    one leg's notional (gross result at the legs' mids minus the net result). adj / adj_out: each leg's price adjustment
    at the entry / the exit (kit v2.1 fix 2, KF-8: a split or a roll inside the trade); adj defaults to
    data.price_factor of each leg at t_in, adj_out to the one at t_out (to adj when adj is given)."""
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
    if adj is None:
        adj = tuple(_default_adj(k_, t_in) for k_ in legs)
        if adj_out is None:
            adj_out = tuple(_default_adj(k_, pd.Timestamp(t_out).floor("h")) for k_ in legs)
    adj_out = tuple(adj) if adj_out is None else tuple(adj_out)
    for key, ls, bi, bo, a_, ao_ in zip(legs, sides, bid_in, bid_out, adj, adj_out):
        ls = ls * side
        s_in = float(spread(key, bi, ti, adj=a_)[0])    # base spread at the bid (as kit.sim.Book at a bid bar's open)
        s_out = float(spread(key, bo, to, at=exit_at, adj=ao_)[0])
        m_in, m_out = bi + s_in / 2, bo + s_out / 2
        cm = float(commission(key, a_, m_in)) * k_spr          # per-unit commission of a share leg (0 otherwise),
        cmo = float(commission(key, ao_, m_out)) * k_spr       # with the minimum per order at the stake notional
        h_in, h_out = k_spr * s_in / 2 + cm, k_spr * s_out / 2 + cmo
        fill = (m_in + h_in) * (1 + slip(key, "mkt", k_slip)) if ls > 0 else (m_in - h_in) * (1 - slip(key, "mkt", k_slip))
        ex = (m_out - h_out) * (1 - slip(key, exit_kind, k_slip)) if ls > 0 else (m_out + h_out) * (1 + slip(key, exit_kind, k_slip))
        net += ls * (ex / fill - 1)
        gross += ls * (m_out / m_in - 1)
        if with_swap:
            sp = spec(key)
            sw += (sp["swap_long"] if ls > 0 else sp["swap_short"]) / 360.0 * nights
            if "dividends" in sp:                               # a share leg's dividends, per unit of its notional
                sw += float(dividends(key, [ls], [1.0], pd.DatetimeIndex([t_in]), pd.DatetimeIndex([t_out]))[0])
        out["fill"].append(fill); out["exit"].append(ex); out["mid_in"].append(m_in); out["mid_out"].append(m_out)
    net -= sw
    out.update(swap=sw, nights=nights, net=net, gross=gross, cost_bp=(gross - net) * 1e4)
    return out
