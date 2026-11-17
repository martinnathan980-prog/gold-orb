"""Idea 005 credit leads equity: in-sample test of the declared rule (declared.json). Output results.json, trials.jsonl."""
import json, os, sys, hashlib
import numpy as np, pandas as pd
from scipy import stats
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import data
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CUT = pd.Timestamp("2022-01-01")
FP = json.load(open(os.path.join(LAB, "r2", "fp_costs.json")))["us500"]
SPREAD_BP = FP["spread"] / FP["spread_ref_price"] * 1e4
SLIP_BP = FP["slip_mkt_bps"]; SWAP_L = FP["swap_long"]
TOTAL_BEFORE = 2500

decl = json.load(open(os.path.join(HERE, "declared.json")))
assert hashlib.sha256(open(os.path.join(HERE, "declared.json"), "rb").read()).hexdigest() == open(os.path.join(HERE, "declared.sha256")).read().strip()
H_ = data.load("HYG").adj; S_ = data.load("SPY").adj; I_ = data.load("IEF").adj; G = data.load("GSPC")
D20 = (G.high - G.low).rolling(20).mean().shift(1)  # known before the open of each day

def signals(c):
    r = pd.concat([H_.pct_change(), S_.pct_change(), I_.pct_change()], axis=1, keys=["h", "s", "i"], sort=True).dropna()
    y = r.h - r.i if c["credit"].startswith("HYG minus") else r.h
    b = (y.rolling(c["beta_win"]).cov(r.s) / r.s.rolling(c["beta_win"]).var()).shift(1)
    res = (y - b * r.s).dropna()
    C = res.rolling(c["W"]).sum()
    lo = C.rolling(250).quantile(c["p"]).shift(1); hi = C.rolling(250).quantile(1 - c["p"]).shift(1)
    sig = pd.Series(np.where(C <= lo, -1, np.where(C >= hi, 1, 0)), C.index)[lo.notna()]
    if c["side"] == "long": sig[sig < 0] = 0
    if c["side"] == "short": sig[sig > 0] = 0
    return sig

gd = G.index
def trade(t_idx, side, H):
    """signal at close of gd[t_idx]; returns dict or None"""
    e, x = t_idx + 1, t_idx + 1 + H
    if x >= len(gd): return None
    pe, px = G.open.iloc[e], G.open.iloc[x]
    d20 = D20.iloc[e]
    if not np.isfinite(d20) or d20 <= 0: return None
    gross = side * (px - pe)
    nights = (gd[x] - gd[e]).days
    cost = pe * (SPREAD_BP + 2 * SLIP_BP) / 1e4 + (pe * SWAP_L / 360 * nights if side > 0 else 0.0)
    return {"signal_day": gd[t_idx], "entry_time": gd[e] + pd.Timedelta(hours=14, minutes=30), "exit_time": gd[x] + pd.Timedelta(hours=14, minutes=30),
            "side": side, "R_gross": gross / d20, "R_net": (gross - cost) / d20, "R_x15": (gross - 1.5 * cost) / d20}

def backtest(sig, H, overlap=False):
    pos = {d: i for i, d in enumerate(gd)}
    out, busy = [], -1
    for d, s in sig.items():
        if s == 0 or d not in pos: continue
        i = pos[d]
        if not overlap and i < busy: continue
        t = trade(i, int(s), H)
        if t is None: continue
        out.append(t); busy = i + 1 + H
    return pd.DataFrame(out)

def pf(x): return x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.inf
def summ(t):
    x = t.R_net.values
    yrs = t.groupby(t.exit_time.dt.year).R_net.sum()
    return {"n": int(len(t)), "PF_gross": round(pf(t.R_gross.values), 4), "PF_net": round(pf(x), 4), "PF_x15": round(pf(t.R_x15.values), 4),
            "mean_R_net": round(x.mean(), 5), "t_net": round(x.mean() / x.std(ddof=1) * np.sqrt(len(x)), 3),
            "years_pos": f"{int((yrs > 0).sum())}/{len(yrs)}", "years_pos_frac": round(float((yrs > 0).mean()), 3),
            "n_long": int((t.side > 0).sum()), "n_short": int((t.side < 0).sum()),
            "PF_net_long": round(pf(t.R_net[t.side > 0].values), 3), "PF_net_short": round(pf(t.R_net[t.side < 0].values), 3)}

res, trades = {}, {}
for c in decl["configurations"]:
    sig = signals(c); t = backtest(sig, c["H"]); trades[c["id"]] = t
    res[c["id"]] = summ(t)
    res[c["id"]]["every_signal_mean_R_net"] = round(backtest(sig, c["H"], overlap=True).R_net.mean(), 5)
    print(c["id"], res[c["id"]], flush=True)
with open(os.path.join(HERE, "trials.jsonl"), "w") as f:
    for k, v in res.items(): f.write(json.dumps({"config": k, **v}) + "\n")

main = trades["01_main"]; M = res["01_main"]
# null: same number of trades, same long/short counts, random signal days (non-overlapping), 2000 draws
rng = np.random.default_rng(5)
days = np.arange(260, len(gd) - 5); days = days[(gd[days] >= main.signal_day.min()) & (gd[days] <= main.signal_day.max())]
nl, ns = M["n_long"], M["n_short"]; H = 3; nulls = []
allR = {s: np.array([np.nan if (r := trade(i, s, H)) is None else r["R_net"] for i in days]) for s in (1, -1)}
for _ in range(2000):
    pick = np.sort(rng.choice(len(days), nl + ns, replace=False)); sides = rng.permutation([1] * nl + [-1] * ns)
    v = np.where(sides > 0, allR[1][pick], allR[-1][pick]); nulls.append(np.nanmean(v))
null_pct = float((np.array(nulls) < M["mean_R_net"]).mean() * 100)

# correlation with the ten (round6 convention)
TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
WEEKS = pd.period_range(pd.Timestamp("2014-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")
CUTU = pd.Timestamp("2022-01-01", tz="UTC")
def weekly(et, R):
    return pd.Series(R).groupby(pd.DatetimeIndex(et).tz_localize(None).to_period("W")).sum().reindex(WEEKS, fill_value=0.0)
tensum = 0
for n_, s_ in TEN:  # round6 correlation.py convention, read with entry_time < 2022-01-01
    t_ = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", f"{n_}__{s_}.parquet"),
                         columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", CUTU)])
    t_ = t_[t_.exit_time < CUTU]; tensum = tensum + weekly(t_.exit_time.dt.tz_convert(None).values, t_.R.values)
corr = float(np.corrcoef(weekly(main.exit_time.values, main.R_net.values).values, tensum.values)[0, 1])

# deflated Sharpe (Bailey & Lopez de Prado), trade-level
N = TOTAL_BEFORE + len(decl["configurations"])
x = main.R_net.values; sr = x.mean() / x.std(ddof=1); T = len(x)
srs = np.array([res[k]["mean_R_net"] / trades[k].R_net.std(ddof=1) for k in res])
V = max(srs.var(ddof=1), 1.0 / (T - 1)); g = 0.5772156649
sr0 = np.sqrt(V) * ((1 - g) * stats.norm.ppf(1 - 1 / N) + g * stats.norm.ppf(1 - 1 / (N * np.e)))
sk, ku = stats.skew(x), stats.kurtosis(x, fisher=False)
dsr = float(stats.norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)))

neigh = [res[k]["PF_net"] for k in res if k != "01_main"]
bars = {"n>=250": M["n"] >= 250, "PF_net>=1.12": M["PF_net"] >= 1.12, "t>=2.5": M["t_net"] >= 2.5,
        "years_pos>=60%": M["years_pos_frac"] >= 0.6, "PF_x15>=1.04": M["PF_x15"] >= 1.04,
        "neighbours_median_PF>=1.06": float(np.median(neigh)) >= 1.06, "every_signal_exp>0": M["every_signal_mean_R_net"] > 0,
        "hold<=5": True, "null>=97.5": null_pct >= 97.5, "corr<=0.30": abs(corr) <= 0.30, "DSR>=0.95": dsr >= 0.95}
out = {"idea": decl["idea"], "configs": res, "main": M, "neighbours_median_PF_net": round(float(np.median(neigh)), 4),
       "null_percentile": round(null_pct, 2), "null_mean_R": round(float(np.mean(nulls)), 5),
       "corr_with_sum_of_ten_2014_2021": round(corr, 4), "deflated_sharpe_prob": round(dsr, 4), "n_trials_total": N,
       "per_year_R_net": {int(k): round(v, 2) for k, v in main.groupby(main.exit_time.dt.year).R_net.sum().items()},
       "bars": {k: bool(v) for k, v in bars.items()}, "all_bars_pass": bool(all(bars.values()))}
json.dump(out, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
print(json.dumps({k: out[k] for k in out if k != "configs"}, indent=1, default=str))
