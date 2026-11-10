"""Single-shot validation (2022-2025) of the two finalists chosen in finalists_preval.json. Run ONCE."""
from harness import *     # noqa
p = os.path.join(RES, "val_results.json")
assert os.path.exists(os.path.join(RES, "finalists_preval.json")), "pre-validation decision missing"
assert not os.path.exists(p), "validation already run: no second look"
out = {}
for name, f in S.FINALISTS.items():
    for sym in f["syms"]:
        label = f"{name}_{sym}"
        val = r2.validate(sym, S.make_orders, f["params"], TRACK, label)
        out[label] = val
        v = val["val"]
        print(f"[VAL {label}] n={v.get('n')} tpy={v.get('trades_per_year')} win={v.get('win_rate')} PF={v.get('pf')} t={v.get('t_stat')} expR={v.get('expectancy_R')} "
              f"yrs={v.get('years_pos')} ddR={v.get('max_dd_R')} L={v.get('long_R')} S={v.get('short_R')} bp={val.get('val_bps_per_trade')} | "
              f"stressPF={val['val_stress'].get('pf')} everyR={val['val_every_signal'].get('expectancy_R')} | criteria={val['val_criteria']}", flush=True)
        print("     by_year:", v.get("by_year_R"), "exits:", v.get("exit_reasons"), flush=True)
        json.dump(out, open(p, "w"), indent=1, default=str)
    r2.free()
