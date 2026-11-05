"""Path dependence of the one-position-at-a-time result (and missed-alert robustness):
(a) taken vs skipped signals (every-signal run vs no_overlap run), IS and VAL;
(b) random dropout of a fraction q of the candidate's own orders (true stop-entry mechanism) before
    no_overlap, 500 seeds per q -> distribution of IS PF/t and VAL PF (one logged gl.cut per q);
(c) cost scaling (commission, slippage and spread all x k; swaps unchanged): IS and VAL PF / t
    (one logged gl.cut) -> what the 'lower-cost broker' status actually changes."""
import json
import time

from common import *  # noqa
from goldlab.sim import Costs

m1 = gl.load_m1("xauusd")
o = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
out = {}
# (a) taken vs skipped
for per, t in (("is", ti), ("val", tv)):
    taken = set(t[t.cost == "normal"].oid)
    ev = t[t.cost == "every"]
    tk, sk = ev[ev.oid.isin(taken)], ev[~ev.oid.isin(taken)]
    a, b = tk.R.to_numpy(), sk.R.to_numpy()
    d = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    out[f"taken_vs_skipped_{per}"] = {"taken": summarize(tk), "skipped": summarize(sk),
                                      "diff_exp": round(float(d), 4), "t_diff": round(float(d / se), 2)}
    print(per, out[f"taken_vs_skipped_{per}"], flush=True)

# (b) dropout
KEEP = ["side", "entry_time", "exit_time", "R", "ret", "hold_min", "reason"]
NSEED = int(os.environ.get("NSEED", 500))
drop = {}
for qd in (0.05, 0.10, 0.20, 0.33):
    t0 = time.time()
    rows, parts = [], []
    for s in range(NSEED):
        rng = np.random.default_rng(424242 + int(qd * 1000) * 7919 + s)
        oo = o[rng.random(len(o)) >= qd]
        t = gl.simulate(m1, oo, no_overlap=True)
        tis = gl.cut(t, "is")
        R = tis.R.to_numpy()
        rows.append({"seed": s, "is_n": len(R), "is_pf": pf(R), "is_t": tstat(R)})
        x = t[t.entry_time >= VA_A - pd.Timedelta(days=15)][KEEP].copy()
        x["seed"] = s
        parts.append(x)
    df = pd.DataFrame(rows).set_index("seed")
    v = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review",
               label=label(f"dropout-q{qd}({NSEED} seeds, VAL PF per seed)"))
    g = v.groupby("seed").R
    df["val_pf"] = g.apply(pf)
    df["val_t"] = g.apply(tstat)
    df["val_n"] = g.size()
    df.to_csv(os.path.join(HERE, f"s05_dropout_q{qd}.csv"))
    qq = lambda c, p: round(float(np.nanpercentile(df[c], p)), 3)
    drop[str(qd)] = {"is_pf_p5_25_50_75_95": [qq("is_pf", p) for p in (5, 25, 50, 75, 95)],
                     "is_t_p5_50_95": [qq("is_t", p) for p in (5, 50, 95)],
                     "val_pf_p5_25_50_75_95": [qq("val_pf", p) for p in (5, 25, 50, 75, 95)],
                     "P(is_pf>=1.1773)": round(float((df.is_pf >= 1.1773).mean()), 3),
                     "P(is_pf>=1.20 & t>=2)": round(float(((df.is_pf >= 1.2) & (df.is_t >= 2)).mean()), 3),
                     "P(val_pf>=1.10)": round(float((df.val_pf >= 1.10).mean()), 3),
                     "P(val_pf<1.0)": round(float((df.val_pf < 1.0).mean()), 3),
                     "secs": round(time.time() - t0, 1)}
    print("dropout", qd, drop[str(qd)], flush=True)
out["dropout"] = drop

# (c) cost scaling
base = Costs()
rows, parts = [], []
for k in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5):
    c = Costs(commission=base.commission * k, slip_bps=base.slip_bps * k, swap_long=base.swap_long,
              swap_short=base.swap_short, spread_mult=k)
    t = gl.simulate(m1, o, costs=c, no_overlap=True)
    tis = gl.cut(t, "is")
    R = tis.R.to_numpy()
    rows.append({"k": k, "is_n": len(R), "is_pf": round(pf(R), 4), "is_t": round(tstat(R), 3), "is_exp": round(float(R.mean()), 4)})
    x = t[t.entry_time >= VA_A - pd.Timedelta(days=15)][KEEP].copy()
    x["k"] = k
    parts.append(x)
v = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review", label=label("cost-scaling k=0..1.5 (VAL PF/t per k)"))
df = pd.DataFrame(rows).set_index("k")
g = v.groupby("k").R
df["val_pf"] = g.apply(pf).round(4)
df["val_t"] = g.apply(tstat).round(3)
df["val_exp"] = g.mean().round(4)
out["cost_scaling"] = df.reset_index().to_dict("records")
print(df, flush=True)
json.dump(out, open(os.path.join(HERE, "s05_paths.json"), "w"), indent=1, default=str)
