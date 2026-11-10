"""Base runs of the finalist: fp / stress / gross, one-position and every-signal; trades saved (IS + VAL separately).
VAL access is logged through gl.cut (track='review')."""
import time
from common import *

t0 = time.time()
m1 = r2.load(SYM)
print("frame", m1.shape, m1.index[0], m1.index[-1], f"{time.time()-t0:.1f}s", flush=True)

out = {}
runs = {}
for mode in ("fp", "gross", "stress"):
    for no_overlap in (True, False):
        t1 = time.time()
        tr = r2.run(SYM, strategy.make_orders, F, mode, no_overlap, m1)
        tag = f"{mode}_{'one' if no_overlap else 'every'}"
        runs[tag] = tr
        print(tag, len(tr), tr.attrs, f"{time.time()-t1:.1f}s", flush=True)
        gc.collect()

for tag, tr in runs.items():
    ti = is_cut(tr)
    tv = val_cut(tr, f"base-{tag}")
    ti.to_parquet(os.path.join(HERE, f"trades_is_{tag}.parquet"))
    tv.to_parquet(os.path.join(HERE, f"trades_val_{tag}.parquet"))
    ri, rv = report(ti), report(tv)
    out[tag] = {"is": ri, "val": rv, "is_bps": bps(ti), "val_bps": bps(tv),
                "is_t_day": cluster_t(ti.R, day_key(ti.entry_time)), "is_t_week": cluster_t(ti.R, week_key(ti.entry_time)),
                "val_t_day": cluster_t(tv.R, day_key(tv.entry_time)), "val_t_week": cluster_t(tv.R, week_key(tv.entry_time)),
                "is_t_week_centered": cluster_t_centered(ti.R, week_key(ti.entry_time)),
                "val_t_week_centered": cluster_t_centered(tv.R, week_key(tv.entry_time))}
    k = ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "total_R", "max_dd_R", "years_pos", "long_n", "long_R", "short_n", "short_R")
    print("==", tag)
    print("  IS :", {q: ri.get(q) for q in k}, "bps", round(bps(ti), 2), ri.get("by_year_R"), ri.get("exit_reasons"))
    print("  VAL:", {q: rv.get(q) for q in k}, "bps", round(bps(tv), 2), rv.get("by_year_R"), rv.get("exit_reasons"))
    print("  t day/week IS:", round(out[tag]["is_t_day"], 2), round(out[tag]["is_t_week"], 2), round(out[tag]["is_t_week_centered"], 2),
          "| VAL:", round(out[tag]["val_t_day"], 2), round(out[tag]["val_t_week"], 2), round(out[tag]["val_t_week_centered"], 2), flush=True)

# the orders themselves (for later nulls): entry_i, side, stop_dist, exit_i + times
o = strategy.make_orders(m1, **F)
o["entry_time"] = m1.index[o.entry_i.to_numpy()]
o["exit_time"] = m1.index[o.exit_i.to_numpy()]
o.to_parquet(os.path.join(HERE, "orders_fp.parquet"))
print("orders", len(o), "IS", int((o.entry_time < IS_END).sum()), "VAL", int((o.entry_time >= IS_END).sum()))
save(out, "base_reports.json")
print(f"done {time.time()-t0:.1f}s")
