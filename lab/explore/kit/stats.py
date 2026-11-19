"""Statistics of the bars (CHARTER.md 'The bars' = PROTOCOL_V3 section 4), the random-entry null, the weekly
correlation with the ten and the deflated Sharpe ratio. Every function works on the trade table of kit.sim."""
import math
import os

import numpy as np
import pandas as pd
from scipy import stats as st

from . import costs as C
from .sim import Book, NS_H, exit_key, outcomes

KIT = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(KIT, "..", ".."))
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
NY = "America/New_York"
EULER = 0.5772156649015329


def pf(R):
    """sum of positive R / |sum of negative R|; no trade = 0; no loss = inf (0 if no gain either)
    (lab/r2/tracks/round6/night_fade/common.py pf)."""
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    if len(R) == 0:
        return 0.0
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else (float("inf") if g > 0 else 0.0)


def t_stat(x):
    x = np.asarray(x, float)
    if len(x) < 2:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / math.sqrt(len(x)))) if s > 0 else float("nan")


def daily_sums(t, col="R"):
    """Sum of R per trading day (17:00 New York) of entry, days with a trade (lab round6 common.daily_sums)."""
    if len(t) == 0:
        return pd.Series(dtype=float)
    return t[col].groupby(C.trading_day(t.entry_time)).sum()


def by_year(t, col="R"):
    """Sum of R per calendar year of entry (lab/goldlab/metrics.py report)."""
    return t[col].groupby(pd.DatetimeIndex(t.entry_time).year).sum()


def market_split(t, col="R"):
    m = t.groupby("market")[col].agg(["sum", "mean", "size"])
    tot = float(t[col].sum())
    share = float(m["sum"].max() / tot) if tot > 0 else float("inf")
    return {"by_market": {k: {"n": int(r["size"]), "sum_R": float(r["sum"]), "mean_R": float(r["mean"])} for k, r in m.iterrows()},
            "markets_positive_frac": float((m["mean"] > 0).mean()), "max_market_share_of_profit": share}


def summary(t):
    """Figures of one trade table (one market or a basket)."""
    if len(t) == 0:
        return {"n": 0}
    yr = by_year(t)
    d = daily_sums(t)
    out = {"n": int(len(t)), "markets": sorted(t.market.unique().tolist()),
           "PF_gross": pf(t.R_gross), "PF": pf(t.R), "PF_stress": pf(t.R_stress),
           "mean_R": float(t.R.mean()), "mean_R_gross": float(t.R_gross.mean()), "mean_R_stress": float(t.R_stress.mean()),
           "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
           "t_trade": t_stat(t.R), "t_daily": t_stat(d), "n_days": int(len(d)),
           "years_positive_frac": float((yr > 0).mean()), "by_year_R": {int(k): float(v) for k, v in yr.items()},
           "hold_tdays_max": int(t.hold_tdays.max()), "hold_h_mean": float(t.hold_h.mean()),
           "exit_reasons": t.reason.value_counts().to_dict(),
           "long_n": int((t.side > 0).sum()), "long_R": float(t.R[t.side > 0].sum()),
           "short_n": int((t.side < 0).sum()), "short_R": float(t.R[t.side < 0].sum())}
    out.update(market_split(t))
    return out


# ------------------------------------------------------------------ random-entry null
def _distinct(rng, n_draws, n_pool, k):
    """(n_draws, k) indices in [0, n_pool), DISTINCT within each draw (k <= n_pool): a uniformly random ordered
    k-tuple of the pool per draw, the sampling of a permutation test. k = 1 is a plain draw."""
    if k == 1:
        return rng.integers(0, n_pool, (n_draws, 1))
    return np.argsort(rng.random((n_draws, n_pool)), axis=1)[:, :k]      # a random ORDER too: which slot gets which day


def _utc_clock(times):
    """Minutes after 00:00 UTC of each time (a list of ints)."""
    t = pd.DatetimeIndex(times)
    t = t.tz_convert("UTC") if t.tz is not None else t.tz_localize("UTC")
    return np.asarray(t.hour * 60 + t.minute)


def _in_span(bk, g):
    """Kit v2.3 (same-year null): the bars of a market that open between the first and the last real entry of the
    rule on that market, both included. A rule that could only trade from November of its first year (its data start
    there) is then compared with the days of November and December, not with the ten months before it existed: without
    this the first and the last partial year bring back the pooling the same-year null is meant to remove (idea 063:
    32 of its trades fall in November and December 2016, the first two months of its data; against all of 2016 they
    counted as timing and a first version of this null gave the rule the 76th percentile, where it stands near the
    50th)."""
    et = pd.DatetimeIndex(g.entry_time)
    et = et.tz_convert("UTC") if et.tz is not None else et.tz_localize("UTC")
    ix = bk.index
    return np.asarray((ix >= et.min()) & (ix <= et.max()))


def _null_joint(trades, books, exit, stop, target, n_draws, rng, within=None):
    """Same-day null for a basket (lead, 2026-11-18): trades of several markets that were decided at the same time
    (same known_at; entry_time if the table has no known_at) are re-entered together on ONE random day, each leg on
    its own market, with its own side and New York clock time, the day drawn uniformly among the days on which every
    leg of the group has a complete trade. Drawing each leg on its own day (the plain null) treats correlated legs
    as independent bets: the null distribution comes out too narrow and noise passes too often (idea 002's run
    measured it; test_lead_joint_null shows 4 identical legs passing the plain null about one time in six).
    within='year' (kit v2.3, information only): the groups of one calendar year (New York, the year of a group's
    earliest leg) that hold the same markets and clocks take DISTINCT random days of that year, inside the span each
    market traded and at the legs' own UTC clocks; a leg without any complete trade in that year raises ValueError.
    Returns (draw means, number of groups with several markets, groups that had no common day and were drawn leg by
    leg, and for within='year' the counts null_test reports as year_*; None otherwise)."""
    pool, tkey = {}, [None] * len(trades)
    tyear = np.zeros(len(trades), np.int64)
    pos = {ix: k for k, ix in enumerate(trades.index)}
    for mk, g in trades.groupby("market"):
        bk = books[mk] if isinstance(books[mk], Book) else Book(books[mk], mk)
        ny = bk.index.tz_convert(NY)
        clock = np.asarray(ny.hour * 60 + ny.minute)
        day = np.asarray(ny.tz_localize(None).normalize().as_unit("ns").asi8 // (24 * NS_H))
        eny = pd.DatetimeIndex(g.entry_time).tz_convert(NY)
        gclock = np.asarray(eny.hour * 60 + eny.minute)
        gside = g.side.to_numpy()
        span = _in_span(bk, g) if within == "year" else None            # kit v2.3: inside the span the rule traded
        uclock, guclock = (_utc_clock(bk.index), _utc_clock(g.entry_time)) if within == "year" else (None, [None] * len(g))
        for c, s, uc in set(zip(gclock.tolist(), gside.tolist(), list(guclock))):
            cand = np.flatnonzero(clock == c) if span is None else np.flatnonzero((clock == c) & (uclock == uc) & span)
            o = outcomes(bk, cand, np.full(len(cand), s), exit, stop, target, scenarios=("net",))
            ok = o["ok"]
            if not ok.any():
                raise ValueError(f"null: no usable random entry for {mk} at clock {c}")
            u, first = np.unique(day[cand[ok]], return_index=True)        # one candidate per day (the first)
            pool[(mk, c, s) if uc is None else (mk, c, s, uc)] = (u, o["net"]["R"][ok][first])
        for ix, c, s, uc, y in zip(g.index, gclock.tolist(), gside.tolist(), list(guclock), np.asarray(eny.year).tolist()):
            tkey[pos[ix]] = (mk, c, s) if uc is None else (mk, c, s, uc)
            tyear[pos[ix]] = y
    gk = trades["known_at"] if "known_at" in trades else trades["entry_time"]
    gk = pd.DatetimeIndex(gk)
    gk = (gk.tz_convert("UTC") if gk.tz is not None else gk.tz_localize("UTC")).as_unit("ns").asi8
    order = np.argsort(gk, kind="stable")
    cuts = np.flatnonzero(np.diff(gk[order])) + 1
    tot = np.zeros(n_draws)
    n_joint = n_fallback = 0
    mk_arr = trades["market"].astype(str).to_numpy()
    if within == "year":
        # Same-year null of a basket (kit v2.3): the groups of one calendar year that hold the same legs (market and
        # clock, whatever their sides) take DISTINCT random days among the days of that year on which every leg has a
        # complete trade, each group keeping its own sides (a permutation test inside the year: the real days are
        # one such choice; a long group and a short group never land on the same day, as in the real rule).
        by_sig, info = {}, {"strata": 0, "replaced": 0, "dense": 0, "room": 0}
        for idxs in np.split(order, cuts):
            n_joint += len(set(mk_arr[idxs])) > 1
            sig = tuple(sorted((tkey[i][0], tkey[i][1], tkey[i][3]) for i in idxs))     # legs without their side
            by_sig.setdefault((int(tyear[idxs].min()), sig), []).append(idxs)       # the group's earliest leg
        for (y, sig), glist in by_sig.items():
            lo, hi = (int(np.datetime64(f"{yy}-01-01", "D").astype(np.int64)) for yy in (y, y + 1))
            legs, common = {}, None
            for k_ in sorted({tkey[i] for idxs in glist for i in idxs}):               # every leg and side present
                u, R = pool[k_]
                m = (u >= lo) & (u < hi)
                if not m.any():
                    raise ValueError(f"null within='year': {k_[0]} has no usable random entry in {y}")
                legs[k_] = (u[m], R[m])
                common = u[m] if common is None else np.intersect1d(common, u[m], assume_unique=True)
            g, n_legs = len(glist), sum(len(idxs) for idxs in glist)
            info["strata"] += 1
            if len(common) == 0:                              # no common day in the year: leg by leg, with replacement
                n_fallback += sum(len(set(mk_arr[idxs])) > 1 for idxs in glist)
                info["replaced"] += n_legs
                for idxs in glist:
                    for i in idxs:
                        u, R = legs[tkey[i]]
                        tot += R[rng.integers(0, len(u), n_draws)]
                continue
            if g <= len(common):
                picks = _distinct(rng, n_draws, len(common), g)
                info["dense"] += n_legs * (2 * g > len(common))
                # room to differ from the real choice: a day left over, or groups with different sides to swap days
                info["room"] += n_legs * (g < len(common) or len({tuple(sorted(tkey[i] for i in idxs)) for idxs in glist}) > 1)
            else:                                             # more groups than days (cannot happen for real trades)
                picks = rng.integers(0, len(common), (n_draws, g))
                info["replaced"] += n_legs
            days = common[picks]
            for j, idxs in enumerate(glist):
                for i in idxs:
                    u, R = legs[tkey[i]]
                    tot += R[np.searchsorted(u, days[:, j])]
        return tot / len(trades), int(n_joint), int(n_fallback), info
    for idxs in np.split(order, cuts):
        legs = [pool[tkey[i]] for i in idxs]
        several = len(set(mk_arr[idxs])) > 1
        n_joint += several
        common = legs[0][0]
        for u, _ in legs[1:]:
            common = np.intersect1d(common, u, assume_unique=True)
        if len(common) == 0:
            n_fallback += several
            for u, R in legs:
                tot += R[rng.integers(0, len(u), n_draws)]
            continue
        pick = common[rng.integers(0, len(common), n_draws)]
        for u, R in legs:
            tot += R[np.searchsorted(u, pick)]
    return tot / len(trades), int(n_joint), int(n_fallback), None


def null_test(trades, books, exit, stop, target=None, mode="every", n_draws=2000, seed=0, joint="auto", within=None):
    """Random-entry null (PROTOCOL_V3 section 4; lab round6 null.py, at hourly resolution): each real trade is re-entered
    on its market, with its side, at the open of a bar with the same New York clock time (hh:mm) on a random day (uniform
    with replacement among that market's bars at that clock time that give a complete trade), with the same exit, stop
    and target rule; net costs. Statistic: the pooled mean net R of each draw; percentile = share of the draw means
    strictly below the real mean, x100. Keeping each trade's side is what guards against a long-only rule passing on a
    market's drift alone.
    mode 'every' (default, as round6 null.py no_overlap=False): every draw is a trade. mode 'one': the one-position
    filter is applied to each draw, with draws that share an entry bar ordered AT RANDOM (never by exit: verifier V2,
    ordering by exit kept the first-stopped loser among colliding opposite draws and pushed the null mean down).
    The result carries `exit_key` (sim.exit_key of exit, stop, target, event times per market): judge.verdict fails the
    null bar unless it equals trades.attrs['exit_key'] (verifier V4: the null must use the main's own exit).
    joint ('auto' by default, mode 'every' only): when trades of several markets were decided at the same time (same
    known_at), the legs of each such group are re-entered together on one random day (_null_joint): a basket whose
    legs move together is one bet per day, not several. A table without such groups takes the plain path below,
    unchanged. joint=False forces the plain null (reported as 'joint_groups': 0).
    within (kit v2.3): None (default) = the JUDGED null above, the random day drawn in the whole sample. 'year' = the
    SAME-YEAR null, INFORMATION ONLY: each real trade is re-entered on a random day of ITS OWN calendar year (New York
    date of its entry; a joint group: the year of its first leg), drawn inside the span the rule traded that market
    (first to last real entry, _in_span: a first or last year the rule only partly covers is not padded with the months
    before it existed), at the same clock in New York AND in UTC (so in the same daylight-saving season), everything
    else the same. The trades of one stratum (market, clock, year; long and short together, each keeping its side) take
    DISTINCT days: a permutation test inside the year, exact when the rule's days are a random choice among the
    stratum's days, also when the rule takes most of them. The result adds 'year_strata', 'year_dense_share' (share of the trades in a stratum where the rule took
    more than half of the days), 'year_room_share' (share of the trades in a stratum with a day left to draw),
    'year_replaced' and 'year_no_room' (the rule took every day of every stratum: the percentile is None, there is
    nothing to compare with). Why: the judged null pools
    every year, so a one-sided rule whose signals bunch in a few years is compared with days of other years, and the
    drift of its own years counts as timing (idea 063, long bitcoin on dear-dollar days, 164 of 351 signals in 2017:
    91st percentile against the whole sample, 52nd against days of the same year). It is stricter than the judged
    null only for that reason; it also removes the credit of a rule that truly picks the good years, so it is read
    beside the judged null, never instead of it. judge.verdict refuses it as `null` and records it as `null_year`.
    The result carries 'within'."""
    if within not in (None, "year"):
        raise ValueError("within is None (the judged null) or 'year' (the same-year null, information only)")
    if within == "year" and mode != "every":
        # the verifier's C3: with the one-position filter the draws that collide are dropped, more of them in the years
        # where the rule trades most, so the null under-weights exactly those years (a rule without timing stood at the
        # 67th percentile on average). The same-year null keeps every draw, as the judged null does by default.
        raise ValueError("the same-year null (within='year') is defined for mode='every' only: the one-position filter "
                         "drops more draws in the years where the rule trades most and shifts the null")
    rng = np.random.default_rng(seed)
    real = float(trades["R"].mean())
    if mode == "every" and joint in ("auto", True) and len(trades):
        gk = pd.DatetimeIndex(trades["known_at"] if "known_at" in trades else trades["entry_time"])
        per_time = pd.Series(trades["market"].astype(str).to_numpy(), index=gk.as_unit("ns").asi8).groupby(level=0).nunique()
        if (per_time > 1).any():
            means, n_joint, n_fb, yinfo = _null_joint(trades, books, exit, stop, target, n_draws, rng, within=within)
            ek = exit_key(exit, stop, target, sorted(trades["market"].astype(str).unique()))
            return _year_info({"real_mean_R": real, "percentile": float((means < real).mean() * 100),
                               "n_draws": int(n_draws), "seed": seed, "exit_key": ek, "mode": mode,
                               "joint_groups": n_joint, "joint_no_common_day": n_fb, "null_mean": float(means.mean()),
                               "null_sd": float(means.std(ddof=1)), "means": means, "within": within}, yinfo, len(trades))
    per_mk = []
    for mk, g in trades.groupby("market"):
        bk = books[mk] if isinstance(books[mk], Book) else Book(books[mk], mk)
        ny = bk.index.tz_convert(NY)
        clock = np.asarray(ny.hour * 60 + ny.minute)
        eny = pd.DatetimeIndex(g.entry_time).tz_convert(NY)
        gclock = np.asarray(eny.hour * 60 + eny.minute)
        gside = g.side.to_numpy()
        byear = np.asarray(ny.year) if within == "year" else None           # each bar's New York year
        gyear = np.asarray(eny.year).tolist() if within == "year" else [None] * len(g)
        span = _in_span(bk, g) if within == "year" else None
        # same-year null: the random day also keeps the trade's UTC clock, so it is a day of the same daylight-saving
        # season (a rule set on a UTC hour is never re-entered an hour early or late, nor one set on a New York hour)
        uclock, guclock = (_utc_clock(bk.index), _utc_clock(g.entry_time).tolist()) if within == "year" else (None, [None] * len(g))
        pools = {}
        for c, s, y, uc in set(zip(gclock.tolist(), gside.tolist(), gyear, guclock)):
            cand = np.flatnonzero(clock == c) if y is None else np.flatnonzero((clock == c) & (uclock == uc) & (byear == y) & span)
            o = outcomes(bk, cand, np.full(len(cand), s), exit, stop, target, scenarios=("net",))
            ok = o["ok"]
            if not ok.any():
                raise ValueError(f"null: no usable random entry for {mk} at clock {c}" + ("" if y is None else f" in {y}"))
            pools[(c, s, y, uc)] = (cand[ok], o["net"]["exit_i"][ok], o["net"]["R"][ok])
        keys = list(zip(gclock.tolist(), gside.tolist(), gyear, guclock))
        per_mk.append((mk, keys, pools, len(bk.t) + 1))
    # draws vectorised across draws; the one-position filter runs trade by trade in entry order with a state per draw
    tot = np.zeros(n_draws)
    cnt = np.zeros(n_draws)
    yinfo = {"strata": 0, "replaced": 0, "dense": 0, "room": 0} if within == "year" else None
    for mk, keys, pools, big in per_mk:
        E = np.empty((n_draws, len(keys)), np.int64)
        X = np.empty_like(E)
        RR = np.empty((n_draws, len(keys)))
        if within == "year":
            # Same-year null (kit v2.3): the trades of one stratum (clock, year; long and short together) take
            # DISTINCT random days of that stratum, each trade keeping its side: a permutation test inside the year,
            # of which the real days are one choice. Drawing with replacement would compare a rule that trades half
            # the days of a year with sets that repeat days (the null too wide, a real timing edge under-read), and
            # letting a long and a short draw share a day would cancel them (the null too narrow).
            strata = {}
            for q, (c, _s, y, uc) in enumerate(keys):
                strata.setdefault((c, y, uc), []).append(q)         # long and short trades of a stratum share its days
            for (c, y, uc), qs in strata.items():
                base = None
                for s_ in sorted({keys[q][1] for q in qs}):         # bars usable for every side present
                    ci = pools[(c, s_, y, uc)][0]
                    base = ci if base is None else np.intersect1d(base, ci, assume_unique=True)
                if len(base) == 0:
                    raise ValueError(f"null within='year': no bar of {mk} at clock {c} in {y} gives a complete trade "
                                     "on every side the rule took")
                yinfo["strata"] += 1
                if len(qs) <= len(base):
                    k = _distinct(rng, n_draws, len(base), len(qs))
                    yinfo["dense"] += len(qs) * (2 * len(qs) > len(base))
                    # room to differ from the real choice: a day left over, or long and short trades to swap days
                    yinfo["room"] += len(qs) * (len(qs) < len(base) or len({keys[q][1] for q in qs}) > 1)
                else:                                               # more trades than days (cannot happen for real trades)
                    k = rng.integers(0, len(base), (n_draws, len(qs)))
                    yinfo["replaced"] += len(qs)
                picked = base[k]                                    # (n_draws, trades of the stratum): bar positions
                for j, q in enumerate(qs):
                    ci, xi, R = pools[keys[q]]
                    at = np.searchsorted(ci, picked[:, j])
                    E[:, q], X[:, q], RR[:, q] = ci[at], xi[at], R[at]
        else:
            for q, c_s in enumerate(keys):
                ci, xi, R = pools[c_s]
                k = rng.integers(0, len(ci), n_draws)
                E[:, q], X[:, q], RR[:, q] = ci[k], xi[k], R[k]
        if mode == "one":
            o = np.lexsort((rng.random(E.shape), E), axis=1)
            E = np.take_along_axis(E, o, 1); X = np.take_along_axis(X, o, 1); RR = np.take_along_axis(RR, o, 1)
            last = np.full(n_draws, -1, np.int64)
            for q in range(E.shape[1]):
                keep = E[:, q] > last
                last = np.where(keep, X[:, q], last)
                tot += np.where(keep, RR[:, q], 0.0)
                cnt += keep
        elif mode == "every":
            tot += RR.sum(1)
            cnt += RR.shape[1]
        else:
            raise ValueError("mode is 'every' or 'one'")
    means = tot / cnt
    pct = float((means < real).mean() * 100)
    ek = exit_key(exit, stop, target, sorted(trades["market"].astype(str).unique()))
    return _year_info({"real_mean_R": real, "percentile": pct, "n_draws": int(n_draws), "seed": seed, "exit_key": ek,
                       "mode": mode, "joint_groups": 0, "joint_no_common_day": 0, "null_mean": float(means.mean()),
                       "null_sd": float(means.std(ddof=1)), "means": means, "within": within}, yinfo, len(trades))


def _year_info(res, yinfo, n_trades):
    """Adds the same-year null's own figures (kit v2.3) to a null result; the judged null (yinfo None) is returned
    as it is, no key added. 'year_strata': strata (market, clock, side, year, or year and legs
    for a basket) drawn; 'year_dense_share': share of the trades that sit in a stratum where the rule took more than
    half of the candidate days; 'year_room_share': share of the trades that sit in a stratum with at least one day
    the rule did not take, or with both long and short trades (which can swap days): only these trades can differ
    between the real result and a draw; when the share is small the percentile speaks of few trades; 'year_replaced': trades drawn with replacement because their stratum had
    fewer days than trades. When the rule took every candidate day of every stratum on one side only, each draw IS
    the real result and the percentile says nothing: it is set to None and 'year_no_room' is True."""
    if yinfo is None:
        return res
    no_room = yinfo["room"] == 0 and yinfo["replaced"] == 0
    res.update(year_strata=int(yinfo["strata"]), year_replaced=int(yinfo["replaced"]),
               year_dense_share=float(yinfo["dense"]) / max(1, n_trades),
               year_room_share=float(yinfo["room"] + yinfo["replaced"]) / max(1, n_trades), year_no_room=bool(no_room))
    if no_room:
        res.update(percentile=None)
    return res


# ------------------------------------------------------------------ correlation with the ten
TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
WEEKS = pd.period_range(pd.Timestamp("2014-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")


def ten_trades(ten_dir=None):
    """The ten rules' official trades, read with entry_time < 2022-01-01 IN the read statement, exits in 2022 dropped
    (lab/r2/tracks/round6/night_fade/correlation.py official)."""
    ten_dir = ten_dir or os.path.join(LAB, "results", "r2", "recalc", "trades")
    out = {}
    for n, s in TEN:
        t = pd.read_parquet(os.path.join(ten_dir, f"{n}__{s}.parquet"), columns=["entry_time", "exit_time", "R"],
                            filters=[("entry_time", "<", IS_END)])
        assert (t.entry_time < IS_END).all()
        out[f"{n}:{s}"] = t[t.exit_time < IS_END]
    return out


def weekly(t, col="R"):
    """Weekly sums of R by exit week (W-SUN periods of the UTC exit time), every calendar week from the week of
    2014-01-01 to the week of 2021-12-31 (418 weeks), a week without an exit = 0 (correlation.py weekly)."""
    w = t.groupby(pd.DatetimeIndex(t.exit_time).tz_convert(None).to_period("W"))[col].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def corr_with_ten(trades, ten=None, ten_dir=None):
    """Pearson rho of the weekly R of `trades` (in-sample exits only) with the weekly sum of the ten. None if constant."""
    assert len(WEEKS) == 418
    ten = ten if ten is not None else ten_trades(ten_dir)
    tot = sum(weekly(v) for v in ten.values())
    if not len(trades):                  # kit v2.1 fix 3 (R3-7): an empty main (exit_time of dtype object) has no
        return None                      # weekly series: the correlation is undefined (the bar fails as missing)
    t = trades[pd.DatetimeIndex(trades.exit_time) < IS_END]
    r = float(np.corrcoef(weekly(t).to_numpy(), tot.to_numpy())[0, 1])
    return None if np.isnan(r) else r


# ------------------------------------------------------------------ deflated Sharpe ratio
def expected_max_z(n_trials):
    """E[max of N standard normals] (Bailey and Lopez de Prado 2014, eq. for SR0 without the scale)."""
    n = max(float(n_trials), 2.0)
    return (1 - EULER) * st.norm.ppf(1 - 1 / n) + EULER * st.norm.ppf(1 - 1 / (n * math.e))


def deflated_sharpe(x, n_trials, var_sr=None):
    """Deflated Sharpe ratio (Bailey and Lopez de Prado, 'The Deflated Sharpe Ratio', 2014) of the per-observation
    series x (per-trade R for one market; daily sums of R for a basket, as the t bar).
    SR0 = sqrt(V) * E[max z of N trials]; DSR = Phi((SR - SR0) sqrt(T-1) / sqrt(1 - g3 SR + (g4-1)/4 SR^2)).
    Variance assumption: V = the variance of the SR estimate of a zero-edge rule observed over the same T periods,
    1/(T-1), unless a larger cross-trial variance is given (var_sr): V = max(1/(T-1), var_sr). Using the sampling
    variance assumes the trials are about as dispersed as pure noise would make them; the Monte Carlo of test_kit.py
    checks that with this V the best of N pure-noise rules reaches DSR >= 0.95 in about 5 % of the worlds or fewer."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    T = len(x)
    if T < 3 or x.std(ddof=1) == 0:
        return {"dsr": float("nan"), "sr": float("nan"), "sr0": float("nan"), "T": T, "n_trials": int(n_trials)}
    sr = float(x.mean() / x.std(ddof=1))
    g3 = float(st.skew(x))
    g4 = float(st.kurtosis(x, fisher=False))
    V = 1.0 / (T - 1)
    if var_sr is not None and np.isfinite(var_sr):
        V = max(V, float(var_sr))
    sr0 = math.sqrt(V) * expected_max_z(n_trials)
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(max(den, 1e-12))
    return {"dsr": float(st.norm.cdf(z)), "sr": sr, "sr0": float(sr0), "T": T, "n_trials": int(n_trials),
            "skew": g3, "kurtosis": g4, "var_sr_used": V}
