"""P8 (run inline once; saved for reproducibility): trailing stop moved only at 4h closes (manual
updates at each alert) + R by the UTC 4h window in which the fill occurred."""
import sys; sys.path.insert(0, "."); sys.path.insert(0, "audit/scratch/donch4h_stop/lookahead")
import numpy as np, pandas as pd
import goldlab as gl, refimpl as RI, refimpl2 as R2
t, c = RI.load_raw()
fr = []
for lab, kw in {"base": {}, "trail_updated_at_4h_closes_only": {"trail_mode": 4, "upd": "bin_last"}}.items():
    x = R2.run(t, c, **kw); x["variant"] = lab; fr.append(x)
allf = pd.concat(fr, ignore_index=True)
isf = allf[(allf.entry_time >= pd.Timestamp("2013-01-01", tz="UTC")) & (allf.entry_time < pd.Timestamp("2022-01-01", tz="UTC"))]
valf = gl.cut(allf, "val", track="review", label="lookahead:donch4h_stop:decision-hour+4h-trail")
for lab in ("base", "trail_updated_at_4h_closes_only"):
    print(f"{lab:34s} IS {R2.stats(isf[isf.variant == lab])}\n{'':34s} VAL {R2.stats(valf[valf.variant == lab])}")
def pf(R):
    R = np.asarray(R); return round(float(R[R > 0].sum() / -R[R < 0].sum()), 2)
for name, d in (("IS", isf[isf.variant == "base"]), ("VAL", valf[valf.variant == "base"])):
    g = d.groupby(d.entry_time.dt.floor("4h").dt.hour).R.agg(["count", "sum", pf])
    g.index.name = "window_start_utc"
    print(name, "R by OCO window (UTC 4h window in which the fill occurred):\n", g.round(2).to_string())
