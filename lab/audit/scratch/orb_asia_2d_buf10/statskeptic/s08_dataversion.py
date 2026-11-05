"""Data-version sensitivity (IS only, no VAL access): the track ran on the unpatched file, the audit on
the patched one.  How many trading days differ, how many IS trades change, and how much of the
PF / t move comes from the path re-shuffle."""
import json

from common import *  # noqa

m1p = gl.load_m1("xauusd")
m1u = pd.read_parquet(os.path.join(LAB, "data", "xauusd_m1_unpatched.parquet"))
out = {}
for nm, f in (("patched", m1p), ("unpatched", m1u)):
    f_is = f[f.index < IS_B]
    cnt = pd.Series(1, index=gl.trading_day(f_is.index)).groupby(level=0).sum()
    out[f"{nm}_is_bars"] = int(len(f_is))
    out[f"{nm}_is_days"] = int(len(cnt))
    out[f"{nm}_is_short_days(<50% median)"] = int((cnt < 0.5 * cnt.median()).sum())
tp = gl.cut(gl.simulate(m1p, S.make_orders(m1p, **PARAMS)), "is")
tu = gl.cut(gl.simulate(m1u, S.make_orders(m1u, **PARAMS)), "is")
kp = set(zip(tp.entry_time, tp.side))
ku = set(zip(tu.entry_time, tu.side))
common = kp & ku
out["is_trades_patched"] = len(tp)
out["is_trades_unpatched"] = len(tu)
out["common_trades(entry_time,side)"] = len(common)
out["only_patched"] = len(kp - ku)
out["only_unpatched"] = len(ku - kp)
out["patched"] = summarize(tp)
out["unpatched"] = summarize(tu)
mp = tp.set_index(["entry_time", "side"]).R
mu = tu.set_index(["entry_time", "side"]).R
cm = sorted(common)
out["R_on_common_trades_patched_minus_unpatched"] = round(float(mp.loc[cm].sum() - mu.loc[cm].sum()), 2)
out["sumR_only_patched"] = round(float(mp.loc[sorted(kp - ku)].sum()), 1)
out["sumR_only_unpatched"] = round(float(mu.loc[sorted(ku - kp)].sum()), 1)
json.dump(out, open(os.path.join(HERE, "s08_dataversion.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
