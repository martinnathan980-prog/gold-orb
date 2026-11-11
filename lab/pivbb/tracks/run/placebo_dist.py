"""Is candidate A's edge the pivot line or the distance? Placebo touches split into lines shifted TOWARDS the market
(closer than R2 / S2) and AWAY from it (further). Descriptive, mid prices, no cost, every signal, in-sample frame only."""
import sys, json, runpy
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
ns = runpy.run_path("/home/user/gold-orb/lab/pivbb/tracks/run/placebo_desc.py", run_name="lib") if False else None
from goldlab import r2
from pivbb.tracks.run import strategy as S
import importlib.util
sp = importlib.util.spec_from_file_location("pd_", "/home/user/gold-orb/lab/pivbb/tracks/run/placebo_walk.py")
m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
walk = m.walk
OUT = "/home/user/gold-orb/lab/results/pivbb/run"
m1 = r2.load("xauusd", end="2022-01-01")
c = S.context(m1)
Treal = S.level_table(c)
prm = dict(levels=["D_R2", "D_S2"], entry="touch")
rows = []
for sd in [None] + list(range(100, 140)):
    o = S.make_orders(m1, **dict(prm, placebo=sd))
    o = o[m1.index[o.entry_i.to_numpy()] >= pd.Timestamp("2013-01-01", tz="UTC")].reset_index(drop=True)
    R = walk(c["o"], c["h"], c["l"], o.entry_i.to_numpy(np.int64), o.exit_i.to_numpy(np.int64), o.side.to_numpy(np.int64), o["stop"].to_numpy(), o.target.to_numpy())
    d = c["day_of"][o.entry_i.to_numpy()]
    real_px = np.where(o.lv_name == "D_R2", Treal["D_R2"][d], Treal["D_S2"][d])
    role = np.where(o.lv_name == "D_R2", 1, -1)
    shift = (o.lv_px.to_numpy() - real_px) / o.atr_d.to_numpy() * role       # > 0: further from the market than the real pivot
    rows.append(pd.DataFrame({"seed": -1 if sd is None else sd, "R": np.clip(R, -1.5, 10), "shift": shift, "outward_break": role * o.side.to_numpy()}))
A = pd.concat(rows, ignore_index=True).dropna()
A["bucket"] = np.where(A.seed < 0, "real R2/S2", np.where(A["shift"] > 0, "placebo, further away (+0.2..0.4 dATR)", "placebo, closer (-0.2..0.4 dATR)"))
tab = A.groupby("bucket").R.agg(n="size", mean_R="mean").round(4)
tab["n_per_seed"] = (tab.n / np.where(tab.index == "real R2/S2", 1, 40)).round(0)
tab["se"] = (A.groupby("bucket").R.std() / np.sqrt(tab.n_per_seed)).round(4)        # standard error for ONE level set
print(tab)
ob = A[A.outward_break == 1].groupby("bucket").R.agg(n="size", mean_R="mean").round(4)
print("outward breaks only (R2 upward, S2 downward):"); print(ob)
# per-seed means inside each bucket -> spread
ps = A[A.seed >= 0].groupby(["bucket", "seed"]).R.mean().groupby("bucket").agg(["mean", "std", "min", "max"]).round(4)
print(ps)
json.dump({"buckets": tab.reset_index().to_dict("records"), "outward_only": ob.reset_index().to_dict("records"), "per_seed_spread": ps.reset_index().to_dict("records")},
          open(OUT + "/placebo_distance_split.json", "w"), indent=1)
