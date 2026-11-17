"""Idea 002, world news tone shock: in-sample test of declared.json (all configurations, costs, null, correlation, DSR).
Reads GDELT daily aggregates (~/explore_data/gdelt, built by fetch_gdelt.py) and Dukascopy H1 via lab/explore/fetch.py.
Everything is cut at 2021-12-31. Writes results.json and trials.jsonl here."""
import glob, hashlib, json, os, sys
import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(LAB, "explore"))
import fetch  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
DECL = json.load(open(os.path.join(HERE, "declared.json")))
SHA = hashlib.sha256(open(os.path.join(HERE, "declared.json"), "rb").read()).hexdigest()
assert SHA == open(os.path.join(HERE, "declared.sha256")).read().strip()
COSTS = json.load(open(os.path.join(LAB, "r2", "fp_costs.json")))
LEGS = [("XAUUSD", "xauusd", +1), ("USDJPY", "usdjpy", -1), ("USA500IDXUSD", "us500", -1), ("DEUIDXEUR", "ger40", -1)]
TOTAL_BEFORE = 2500


def tone_series():
    rows = {}
    for f in glob.glob(os.path.expanduser("~/explore_data/gdelt/*.json")):
        d = pd.Timestamp(os.path.basename(f)[:8])
        if d >= pd.Timestamp("2022-01-01"):
            continue
        j = json.load(open(f))
        if j.get("missing") or not j.get("n"):
            continue
        rows[d] = (j["tone_msum"] / j["mentions"], j["tone_sum"] / j["n"])
    t = pd.DataFrame(rows, index=["w", "u"]).T.sort_index()
    return t


def zscore(s, window):
    idx = pd.date_range(s.index[0], s.index[-1], freq="D")
    s = s.reindex(idx)
    roll = s.shift(1).rolling(window, min_periods=int(window * 50 / 60))
    return ((s - roll.mean()) / roll.std()).dropna()


class Leg:
    def __init__(self, sym, key, side):
        self.sym, self.key, self.side = sym, key, side
        h = fetch.dukascopy_h1(sym)
        self.h = h
        self.t = h.index.values
        self.o = h.open.to_numpy()
        day = h.groupby(h.index.floor("D")).agg(hi=("high", "max"), lo=("low", "min"), n=("open", "size"))
        day = day[day.n >= 10]
        rng = (day.hi - day.lo)
        self.d20 = rng.rolling(20).mean().shift(1)  # indexed by UTC day; value = mean of the 20 days before
        self.c = COSTS[key]

    def trade(self, D, hold):
        et = D + pd.Timedelta(days=1, hours=7)
        i = np.searchsorted(self.t, np.datetime64(et.tz_localize("UTC").tz_convert(None)))
        if i >= len(self.t):
            return None
        ent = pd.Timestamp(self.t[i], tz="UTC")
        xt = ent + pd.offsets.BDay(hold)
        j = np.searchsorted(self.t, np.datetime64(xt.tz_convert(None)))
        if j >= len(self.t):
            return None
        ext = pd.Timestamp(self.t[j], tz="UTC")
        d20 = self.d20.get(ent.floor("D"), np.nan)
        if not np.isfinite(d20) or d20 <= 0:
            k = self.d20.index.searchsorted(ent.floor("D"))
            d20 = self.d20.iloc[k - 1] if k > 0 else np.nan
        if not np.isfinite(d20) or d20 <= 0:
            return None
        pe, px = self.o[i], self.o[j]
        c = self.c
        spread = c["spread"] / c["spread_ref_price"] * pe if "spread_ref_price" in c else c["spread"]
        slip = c["slip_mkt_bps"] * 1e-4 * (pe + px)
        rate = c["swap_long"] if self.side > 0 else c["swap_short"]
        nights = 0
        for d in pd.date_range(ent.floor("D"), ext.floor("D"), freq="D"):
            cross = d + pd.Timedelta(hours=22)
            if ent < cross <= ext and d.weekday() < 5:
                nights += 3 if d.strftime("%a") == c["swap_triple"] else 1
        swap = rate / 360 * pe * nights
        gross = self.side * (px - pe) / d20
        cost = (spread + slip + swap) / d20
        return dict(leg=self.key, signal_day=D, entry_time=ent, exit_time=ext, R_gross=gross, cost_R=cost,
                    R=gross - cost, R15=gross - 1.5 * cost)


def run_cfg(legs, days, hold, overlap=True):
    out = []
    for L in legs:
        busy = None
        for D in days:
            tr = L.trade(D, hold)
            if tr is None or tr["exit_time"] >= CUT:
                continue
            if overlap and busy is not None and tr["entry_time"] < busy:
                continue
            busy = tr["exit_time"]
            out.append(tr)
    return pd.DataFrame(out)


def pf(x):
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("inf")


def summary(t):
    if len(t) == 0:
        return {"n": 0}
    daily = t.groupby(t.exit_time.dt.floor("D"))["R"].sum()
    tt = float(daily.mean() / daily.std(ddof=1) * np.sqrt(len(daily)))
    yr = t.groupby(t.exit_time.dt.year)["R"].sum()
    leg = t.groupby("leg")["R"].sum()
    tot = t.R.sum()
    return {"n": int(len(t)), "signals": int(t.signal_day.nunique()), "PF_gross": round(pf(t.R_gross), 3),
            "PF_net": round(pf(t.R), 3), "PF_x1.5": round(pf(t.R15), 3), "mean_R_net": round(float(t.R.mean()), 4),
            "t_daily": round(tt, 2), "years_positive": f"{int((yr > 0).sum())}/{len(yr)}",
            "years_pos_frac": float((yr > 0).mean()), "by_year": yr.round(2).to_dict(),
            "by_leg_R": leg.round(2).to_dict(), "markets_pos_frac": float((leg > 0).mean()),
            "max_leg_share_of_profit": round(float(leg.max() / tot), 3) if tot > 0 else None}


def sharpe_daily(t, span):
    d = t.groupby(t.exit_time.dt.floor("D"))["R"].sum().reindex(span, fill_value=0.0)
    return d.mean() / d.std(ddof=1), d


def dsr(sr, srs_all, n_trials, series):
    T = len(series)
    sk, ku = stats.skew(series), stats.kurtosis(series, fisher=False)
    V = np.var(srs_all, ddof=1)
    g = 0.5772156649
    sr0 = np.sqrt(V) * ((1 - g) * stats.norm.ppf(1 - 1 / n_trials) + g * stats.norm.ppf(1 - 1 / (n_trials * np.e)))
    z = (sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    return float(stats.norm.cdf(z)), float(sr0)


def correlation(t):
    WEEKS = pd.period_range(pd.Timestamp("2014-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")
    TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
    wk = lambda x: x.groupby(x.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum().reindex(WEEKS, fill_value=0.0)
    ten = 0
    for n, s in TEN:
        x = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", f"{n}__{s}.parquet"),
                            columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", CUT)])
        x = x[x.exit_time < CUT]
        ten = ten + wk(x)
    tm = t[t.exit_time >= pd.Timestamp("2014-01-01", tz="UTC")]
    return float(np.corrcoef(wk(tm).to_numpy(), ten.to_numpy())[0, 1])


def main():
    tone = tone_series()
    legs = [Leg(*l) for l in LEGS]
    res, trials, frames = {}, [], {}
    for cfg in DECL["configurations"]:
        s = tone["w"] if cfg["tone"] == "mention_weighted" else tone["u"]
        z = zscore(s, cfg["window"])
        days = list(z.index[z <= cfg["z"]])
        t = run_cfg(legs, days, cfg["hold_bdays"])
        frames[cfg["id"]] = t
        res[cfg["id"]] = summary(t)
        trials.append({"id": cfg["id"], **{k: res[cfg["id"]].get(k) for k in ("n", "PF_net", "t_daily", "PF_x1.5")}})
    main_id = "01_main"
    cfg = DECL["configurations"][0]
    z = zscore(tone["w"], cfg["window"])
    days_main = list(z.index[z <= cfg["z"]])
    allsig = run_cfg(legs, days_main, cfg["hold_bdays"], overlap=False)
    tm = frames[main_id]
    # null: same number of random signal days among eligible days
    elig = np.array(z.index)
    rng = np.random.default_rng(2)
    # precompute trades for every eligible day
    pre = {L.key: {} for L in legs}
    for L in legs:
        for D in elig:
            tr = L.trade(pd.Timestamp(D), cfg["hold_bdays"])
            if tr is not None and tr["exit_time"] < CUT:
                pre[L.key][pd.Timestamp(D)] = (tr["entry_time"], tr["exit_time"], tr["R"])
    nulls = []
    for _ in range(2000):
        ds = sorted(pd.Timestamp(x) for x in rng.choice(elig, len(days_main), replace=False))
        rs = []
        for L in legs:
            busy = None
            for D in ds:
                tr = pre[L.key].get(D)
                if tr is None or (busy is not None and tr[0] < busy):
                    continue
                busy = tr[1]; rs.append(tr[2])
        nulls.append(np.mean(rs))
    null_pct = float((np.array(nulls) < tm.R.mean()).mean() * 100)
    span = pd.date_range("2013-07-01", "2021-12-31", freq="B", tz="UTC")
    srs = [sharpe_daily(f, span)[0] for f in frames.values() if len(f)]
    sr, ser = sharpe_daily(tm, span)
    n_tot = TOTAL_BEFORE + len(DECL["configurations"])
    dprob, sr0 = dsr(sr, srs, n_tot, ser.to_numpy())
    rho = correlation(tm)
    neigh = [res[k]["PF_net"] for k in res if k != main_id and res[k].get("n")]
    m = res[main_id]
    bars = {"t>=2.5": m["t_daily"] >= 2.5, "PF>=1.12": m["PF_net"] >= 1.12, "PF_x1.5>=1.04": m["PF_x1.5"] >= 1.04,
            "years>=60%": m["years_pos_frac"] >= 0.6, "markets>=65%": m["markets_pos_frac"] >= 0.65,
            "max_leg_share<=25%": (m["max_leg_share_of_profit"] or 9) <= 0.25,
            "null>=97.5": null_pct >= 97.5, "neighbours_median_PF>=1.06": float(np.median(neigh)) >= 1.06,
            "every_signal_exp>0": float(allsig.R.mean()) > 0, "corr<=0.30": abs(rho) <= 0.30, "DSR>=0.95": dprob >= 0.95}
    out = {"idea": DECL["idea"], "declared_sha256": SHA, "tone_days": int(len(tone)),
           "tone_span": [str(tone.index[0].date()), str(tone.index[-1].date())], "configs": res,
           "main": {"null_percentile": round(null_pct, 1), "every_signal_n": int(len(allsig)),
                    "every_signal_mean_R": round(float(allsig.R.mean()), 4), "neighbours_median_PF": round(float(np.median(neigh)), 3),
                    "corr_with_sum_of_ten": round(rho, 3), "sharpe_daily": round(float(sr), 4), "dsr_sr0": round(sr0, 4),
                    "deflated_probability": round(dprob, 3), "n_trials_total": n_tot},
           "bars": bars, "pass_all": bool(all(bars.values()))}
    json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    with open(os.path.join(HERE, "trials.jsonl"), "w") as f:
        for r in trials:
            f.write(json.dumps(r) + "\n")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
