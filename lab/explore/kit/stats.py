"""Statistics of the bars (CHARTER.md 'The bars' = PROTOCOL_V3 section 4), the random-entry null, the weekly
correlation with the ten and the deflated Sharpe ratio. Every function works on the trade table of kit.sim."""
import math
import os

import numpy as np
import pandas as pd
from scipy import stats as st

from . import costs as C
from .sim import Book, NS_H, outcomes

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
def null_test(trades, books, exit, stop, target=None, mode="every", n_draws=2000, seed=0):
    """Random-entry null (PROTOCOL_V3 section 4; lab round6 null.py, at hourly resolution): each real trade is re-entered
    on its market, with its side, at the open of a bar with the same New York clock time (hh:mm) on a random day (uniform
    with replacement among that market's bars at that clock time that give a complete trade), with the same exit, stop
    and target rule; net costs. Statistic: the pooled mean net R of each draw; percentile = share of the draw means
    strictly below the real mean, x100. Keeping each trade's side is what guards against a long-only rule passing on a
    market's drift alone.
    mode 'every' (default, as round6 null.py no_overlap=False): every draw is a trade. mode 'one': the one-position
    filter is applied to each draw, with draws that share an entry bar ordered AT RANDOM (never by exit: verifier V2,
    ordering by exit kept the first-stopped loser among colliding opposite draws and pushed the null mean down)."""
    rng = np.random.default_rng(seed)
    real = float(trades["R"].mean())
    per_mk = []
    for mk, g in trades.groupby("market"):
        bk = books[mk] if isinstance(books[mk], Book) else Book(books[mk], mk)
        ny = bk.index.tz_convert(NY)
        clock = np.asarray(ny.hour * 60 + ny.minute)
        eny = pd.DatetimeIndex(g.entry_time).tz_convert(NY)
        gclock = np.asarray(eny.hour * 60 + eny.minute)
        gside = g.side.to_numpy()
        pools = {}
        for c, s in set(zip(gclock.tolist(), gside.tolist())):
            cand = np.flatnonzero(clock == c)
            o = outcomes(bk, cand, np.full(len(cand), s), exit, stop, target, scenarios=("net",))
            ok = o["ok"]
            if not ok.any():
                raise ValueError(f"null: no usable random entry for {mk} at clock {c}")
            pools[(c, s)] = (cand[ok], o["net"]["exit_i"][ok], o["net"]["R"][ok])
        keys = list(zip(gclock.tolist(), gside.tolist()))
        per_mk.append((mk, keys, pools, len(bk.t) + 1))
    # draws vectorised across draws; the one-position filter runs trade by trade in entry order with a state per draw
    tot = np.zeros(n_draws)
    cnt = np.zeros(n_draws)
    for mk, keys, pools, big in per_mk:
        E = np.empty((n_draws, len(keys)), np.int64)
        X = np.empty_like(E)
        RR = np.empty((n_draws, len(keys)))
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
    return {"real_mean_R": real, "percentile": pct, "n_draws": int(n_draws), "seed": seed,
            "mode": mode, "null_mean": float(means.mean()), "null_sd": float(means.std(ddof=1)), "means": means}


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
