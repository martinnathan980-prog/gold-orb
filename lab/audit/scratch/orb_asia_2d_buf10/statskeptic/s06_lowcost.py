"""What does a 'lower-cost broker' change, done consistently?  The spread is scaled IN THE M1 FRAME
before make_orders (so range extremes and first touches are computed with the scenario's quotes),
then commission / slippage are scaled in the simulator.  Compared with the naive way (spread_mult
applied only inside simulate on orders built with the original quotes), which silently drops fills
because each pending order is live only on its pre-computed touch bar.  One logged VAL cut."""
import json

from common import *  # noqa
from goldlab.sim import Costs

m1 = gl.load_m1("xauusd")
KEEP = ["side", "entry_time", "exit_time", "R", "ret", "hold_min", "reason"]
base = Costs()


def scaled_frame(k):
    f = m1.copy()
    half = (f["ac"].to_numpy() - f["bc"].to_numpy()) * (k - 1) / 2
    for c in ("bo", "bh", "bl", "bc"):
        f[c] = f[c].to_numpy() - half
    for c in ("ao", "ah", "al", "ac"):
        f[c] = f[c].to_numpy() + half
    return f


rows, parts = [], []
SCEN = [("prereg", 1.0, 1.0, "consistent"), ("comm+slip x0.5, spread x1", 1.0, 0.5, "consistent"),
        ("all x0.75", 0.75, 0.75, "consistent"), ("all x0.6", 0.6, 0.6, "consistent"),
        ("all x0.5", 0.5, 0.5, "consistent"), ("all x0.75 NAIVE", 0.75, 0.75, "naive")]
o_base = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
for name, ks, kc, mode in SCEN:
    c = Costs(commission=base.commission * kc, slip_bps=base.slip_bps * kc, swap_long=base.swap_long,
              swap_short=base.swap_short, spread_mult=1.0 if mode == "consistent" else ks)
    if mode == "consistent":
        f = m1 if ks == 1.0 else scaled_frame(ks)
        o = S.make_orders(f, **PARAMS)
        t = gl.simulate(f, o, costs=c, no_overlap=True)
        n_orders = len(o)
        if f is not m1:
            del f
    else:
        t = gl.simulate(m1, o_base, costs=c, no_overlap=True)
        n_orders = len(o_base)
    tis = gl.cut(t, "is")
    R = tis.R.to_numpy()
    rows.append({"scenario": name, "orders": n_orders, "nofill": int(t.attrs.get("nofill", 0)), "is_n": len(R),
                 "is_pf": round(pf(R), 4), "is_t": round(tstat(R), 3), "is_exp": round(float(R.mean()), 4)})
    x = t[t.entry_time >= VA_A - pd.Timedelta(days=15)][KEEP].copy()
    x["scenario"] = name
    parts.append(x)
    print(rows[-1], flush=True)
v = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review",
           label=label("low-cost scenarios consistent (spread scaled in frame before make_orders) vs naive"))
df = pd.DataFrame(rows).set_index("scenario")
g = v.groupby("scenario").R
df["val_n"] = g.size()
df["val_pf"] = g.apply(pf).round(4)
df["val_t"] = g.apply(tstat).round(3)
df["val_exp"] = g.mean().round(4)
print(df.to_string())
json.dump(df.reset_index().to_dict("records"), open(os.path.join(HERE, "s06_lowcost.json"), "w"), indent=1, default=str)
