"""What a ~10-month 2026 holdout can and cannot tell us.

Distributions of the 10-month PF (n ~ Poisson(50) trades) under:
  H1        edge as measured: candidate's pooled IS+VAL trades (mean +0.115 R)
  H1/2      half the measured edge (R shifted so the mean is +0.058)
  H0        zero edge after costs (R shifted to mean 0)
  H0rand    random-entry cost drag (R shifted to mean -0.045; N1 null IS/VAL means -0.054/-0.039)
for i.i.d. trades and for 2-week block resampling; plus EMPIRICAL rolling 10-month windows of
(a) the candidate itself 2013-2025 and (b) N1 / N3 null runs (one logged VAL cut).
Likelihood ratios for outcome bins and posterior P(real) for a range of priors."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

rng = np.random.default_rng(2026)
ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
T = pd.concat([ti[ti.variant == "normal"], tv[tv.variant == "normal"]]).sort_values("entry_time")
R = T.R.to_numpy()
mu = R.mean()
NT = 50
B = 40000
bins = [0, 0.6, 0.8, 1.0, 1.2, 1.5, np.inf]
out = {"pooled_mean_R": round(float(mu), 4), "n_pooled": len(R), "trades_per_10m": NT}


def draws_iid(Rs):
    n = rng.poisson(NT, B)
    return np.array([pf(Rs[rng.integers(0, len(Rs), k)]) for k in n])


wk = T.entry_time.dt.tz_convert(None).dt.to_period("2W")
blocks = [g.R.to_numpy() for _, g in T.groupby(wk)]
nb = len(blocks)
nblk_10m = 22   # ~ 10 months of 2-week blocks


def draws_block(shift):
    res = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, nb, nblk_10m)
        res[b] = pf(np.concatenate([blocks[i] for i in pick]) + shift)
    return res


hyp = {"H1": 0.0, "H1/2": -mu / 2, "H0": -mu, "H0rand": -mu - 0.045}
D = {}
for h, sh in hyp.items():
    D[h + "|iid"] = draws_iid(R + sh)
    D[h + "|block2w"] = draws_block(sh)


def summ(x):
    x = x[np.isfinite(x)]
    return {"pf_q5_25_50_75_95": [round(float(np.percentile(x, p)), 2) for p in (5, 25, 50, 75, 95)],
            "P_pf>1": round(float((x > 1).mean()), 3), "P_pf>1.2": round(float((x > 1.2).mean()), 3),
            "P_pf<0.8": round(float((x < 0.8).mean()), 3), "P_pf<0.6": round(float((x < 0.6).mean()), 3),
            "bins": [round(float(((x >= a) & (x < b)).mean()), 3) for a, b in zip(bins[:-1], bins[1:])]}


out["dists"] = {k: summ(v) for k, v in D.items()}
# empirical rolling 10-month windows of the candidate
t2 = T.set_index(T.entry_time.dt.tz_convert(None))
months = pd.period_range("2013-01", "2025-12", freq="M")
roll = []
for i in range(len(months) - 9):
    a, b = months[i].start_time, months[i + 9].end_time
    r = t2.R[(t2.index >= a) & (t2.index <= b)].to_numpy()
    roll.append(pf(r))
roll = np.array(roll)
out["candidate_rolling10m"] = summ(roll)
out["candidate_rolling10m"]["n_windows"] = len(roll)

# empirical null windows: N1 (random time/side) and N3 (signal times, random side), 40 seeds each
m1 = gl.load_m1("xauusd")
g = h4_grid(m1)
cand = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
ent = cand["trig_i"].to_numpy() + 1
kk = (ent < cand["exit_i"].to_numpy()) & (ent < len(m1))
c3 = cand[kk].reset_index(drop=True)
ent = ent[kk]
parts = []
for s in range(40):
    r1 = np.random.default_rng(55_000 + s)
    o1 = random_orders(g, r1, 0.05)
    t1 = gl.simulate(m1, o1, no_overlap=True)
    t1["fam"], t1["seed"] = "N1", s
    side = np.where(r1.random(len(c3)) < 0.5, 1, -1)
    o3 = pd.DataFrame({"entry_i": ent, "side": side, "etype": 0, "stop_dist": 2 * c3.atr.to_numpy(),
                       "trail": 2 * c3.atr.to_numpy(), "exit_i": c3.exit_i.to_numpy()})
    t3 = gl.simulate(m1, o3, no_overlap=True)
    t3["fam"], t3["seed"] = "N3", s
    parts += [t1, t3]
allt = pd.concat(parts, ignore_index=True)
nul = pd.concat([gl.cut(allt, "is"), gl.cut(allt, "val", track="review", label=label("holdout-H0-windows(N1,N3 x40 seeds)"))])
for fam in ("N1", "N3"):
    res = []
    for s, gs in nul[nul.fam == fam].groupby("seed"):
        x = gs.set_index(gs.entry_time.dt.tz_convert(None)).R
        for i in range(0, len(months) - 9, 3):
            a, b = months[i].start_time, months[i + 9].end_time
            r = x[(x.index >= a) & (x.index <= b)].to_numpy()
            if len(r) > 5:
                res.append(pf(r))
    out[f"null_{fam}_rolling10m"] = summ(np.array(res))
    out[f"null_{fam}_rolling10m"]["n_windows"] = len(res)

# likelihood ratios per outcome bin, posterior for several priors
lab_bins = ["<0.6", "0.6-0.8", "0.8-1.0", "1.0-1.2", "1.2-1.5", ">=1.5"]
lr = {}
for h1 in ("H1|block2w", "H1/2|block2w"):
    for h0 in ("H0|block2w", "H0rand|block2w"):
        p1 = np.array(out["dists"][h1]["bins"])
        p0 = np.array(out["dists"][h0]["bins"])
        lr[f"{h1} vs {h0}"] = {b: round(float(a / max(c, 1e-4)), 2) for b, a, c in zip(lab_bins, p1, p0)}
        P1, P0 = out["dists"][h1]["P_pf>1"], out["dists"][h0]["P_pf>1"]
        lr[f"{h1} vs {h0}"]["PF>1 (protocol pass)"] = round(P1 / P0, 2)
        lr[f"{h1} vs {h0}"]["PF<=1 (protocol fail)"] = round((1 - P1) / (1 - P0), 2)
out["likelihood_ratios"] = lr
post = {}
for prior in (0.10, 0.15, 0.25, 0.40):
    row = {}
    L = lr["H1|block2w vs H0|block2w"]
    for b in lab_bins + ["PF>1 (protocol pass)", "PF<=1 (protocol fail)"]:
        o = prior / (1 - prior) * L[b]
        row[b] = round(o / (1 + o), 2)
    post[prior] = row
out["posterior_H1_vs_H0"] = post
json.dump(out, open(os.path.join(HERE, "s07_holdout.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
