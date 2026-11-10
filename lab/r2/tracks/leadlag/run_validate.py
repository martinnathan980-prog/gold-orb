"""Single-shot validation (2022-2025) of the finalist decided in finalists_preval.json. Run ONCE."""
from common import *
import json
out_p = os.path.join(RES, "validation_nq_btc.json")
assert not os.path.exists(out_p), "validation already run"
assert os.path.exists(os.path.join(RES, "finalists_preval.json"))
name = "nq_btc_follow"
f = strategy.FINALISTS[name]
res = {}
for sym in f["syms"]:
    use(sym)
    val = r2.validate(sym, strategy.make_orders, f["params"], TRACK, name)
    res[sym] = val
    v = val["val"]
    print(sym, "VAL:", json.dumps({k: v.get(k) for k in ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "years_pos", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_dd_R", "total_R")}))
    print("   by year R:", v.get("by_year_R"), "| exits:", v.get("exit_reasons"), "| bps/trade:", val["val_bps_per_trade"])
    print("   stress:", {k: val["val_stress"].get(k) for k in ("n", "pf", "expectancy_R", "t_stat")})
    print("   every signal:", {k: val["val_every_signal"].get(k) for k in ("n", "pf", "expectancy_R", "t_stat")})
    print("   criteria:", val["val_criteria"])
json.dump({"finalist": name, "params": f["params"], "results": res}, open(out_p, "w"), indent=1, default=str)
