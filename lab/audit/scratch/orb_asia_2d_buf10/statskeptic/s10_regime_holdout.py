"""Holdout interpretation conditional on the (strategy-independent) 2026 gold regime: PF of rolling
10-month windows of the candidate (H1 as measured) and of the zero-net shift (H0_zero), split by the
window's absolute gold return.  Uses s01 trades (VAL part came from one logged cut)."""
import json
from common import *  # noqa
ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet")); tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
TA = pd.concat([ti[ti.cost == "normal"], tv[tv.cost == "normal"]])
m1 = gl.load_m1("xauusd")
mc = ((m1.bc + m1.ac) / 2).resample("ME").last()
mc.index = mc.index.tz_convert(None).to_period("M")
MONTHS = pd.period_range("2013-01", "2025-12", freq="M"); W = 10
code = MONTHS.get_indexer(TA.entry_time.dt.tz_convert(None).dt.to_period("M")); R = TA.R.to_numpy(); mu = R.mean()
def win(Rs):
    pos = np.bincount(code, weights=np.where(Rs > 0, Rs, 0), minlength=len(MONTHS)); neg = np.bincount(code, weights=np.where(Rs < 0, -Rs, 0), minlength=len(MONTHS))
    cp, cn = np.r_[0, np.cumsum(pos)], np.r_[0, np.cumsum(neg)]
    return (cp[W:] - cp[:-W]) / (cn[W:] - cn[:-W])
pf1, pf0 = win(R), win(R - mu)
start = MONTHS[:len(MONTHS) - W + 1]
prev = [p - 1 for p in start]; endm = [p + W - 1 for p in start]
gret = np.array([mc.get(e, np.nan) / mc.get(s, np.nan) - 1 if s in mc.index else np.nan for s, e in zip(prev, endm)])
gret[0] = mc[endm[0]] / mc[MONTHS[0]] - 1
out = {}
for nm, lo, hi in (("|gold 10m ret|<5%", 0, .05), ("5-15%", .05, .15), (">=15%", .15, 9)):
    k = (np.abs(gret) >= lo) & (np.abs(gret) < hi)
    out[nm] = {"windows": int(k.sum()), "H1_P(pf>1)": round(float((pf1[k] > 1).mean()), 3), "H1_pf_median": round(float(np.median(pf1[k])), 3),
               "H0zero_P(pf>1)": round(float((pf0[k] > 1).mean()), 3), "H0zero_pf_median": round(float(np.median(pf0[k])), 3)}
out["spearman(window pf, |gold ret|)"] = round(float(pd.Series(pf1).corr(pd.Series(np.abs(gret)), method="spearman")), 3)
json.dump(out, open(os.path.join(HERE, "s10_regime_holdout.json"), "w"), indent=1); print(json.dumps(out, indent=1))
