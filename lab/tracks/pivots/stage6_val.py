"""Stage 6: the ONE validation run (2022-2025) of the finalist chosen on IS.  No re-tuning after this."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy as S
import goldlab as gl
from goldlab.evalkit import stressed_costs, val_criteria
from harness import OUT, fmt

NAME = "rn100_break_fresh"
if __name__ == "__main__":
    m1 = gl.load_m1("xauusd")                      # full history (IS part = ATR warm-up / consistency)
    prm = S.FINALISTS[NAME]
    o = S.make_orders(m1, **prm)
    t = gl.simulate(m1, o)
    ts = gl.simulate(m1, o, costs=stressed_costs("xauusd", 1.5))
    t_is = gl.cut(t, "is")
    print("IS consistency (full frame):", fmt(gl.report(t_is)))
    tv = gl.cut(t, "val", track="pivots", label=NAME)
    tvs = gl.cut(ts, "val", track="pivots", label=NAME + "/stress1.5")
    rv, rvs = gl.report(tv), gl.report(tvs)
    cv = val_criteria(rv)
    print("VAL:", fmt(rv, rvs))
    print("VAL by year:", rv.get("by_year_R"), "exits:", rv.get("exit_reasons"))
    print("VAL criteria:", cv)
    tv = tv.assign(yr=tv.entry_time.dt.year)
    by = tv.pivot_table(index="yr", columns="side", values="R", aggfunc=["count", "sum"]).round(1)
    print(by.T.to_string())
    tv.to_csv(os.path.join(OUT, "val_trades_rn100_break_fresh.csv"))
    t_is.to_csv(os.path.join(OUT, "is_trades_rn100_break_fresh.csv"))
    json.dump({"val": rv, "val_stress_pf": rvs.get("pf"), "val_criteria": cv,
               "val_by_year_side": {f"{a}|{b}|{c}": v for (a, b, c), v in by.unstack().to_dict().items()}
               if False else None},
              open(os.path.join(OUT, "stage6_val.json"), "w"), indent=1, default=str)
