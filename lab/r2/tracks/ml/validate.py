"""Single-shot validation (2022-2025) of the two finalists fixed in results/r2/ml/finalists_preval.json.
Run ONCE. Frozen model, frozen parameters."""
import json
import sys

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa

out_path = os.path.join(RES, "val_results.json")
assert not os.path.exists(out_path), "validation already run"
assert os.path.exists(os.path.join(RES, "finalists_preval.json"))
res = {}
for sym in ["btcusd", "ethusd"]:
    for name, f in S.FINALISTS.items():
        assert sym in f["syms"]
        v = r2.validate(sym, S.make_orders, f["params"], TRACK, f"{name}:{sym}")
        res.setdefault(name, {})[sym] = v
        r = v["val"]
        print(f"{name:22s} {sym} | n={r['n']} PF={r['pf']} expR={r['expectancy_R']} t={r['t_stat']} yrs={r['years_pos']} win={r['win_rate']} "
              f"L={r['long_R']}({r['long_n']}) S={r['short_R']}({r['short_n']}) by_year={r['by_year_R']} bps={v['val_bps_per_trade']}")
        print(f"{'':22s}        stress PF={v['val_stress']['pf']} every-signal expR={v['val_every_signal']['expectancy_R']} (n={v['val_every_signal']['n']}, PF={v['val_every_signal']['pf']}) criteria={v['val_criteria']}")
    r2.free()
json.dump(res, open(out_path, "w"), indent=1, default=str)
