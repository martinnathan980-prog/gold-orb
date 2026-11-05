"""Coordinator-requested diagnostic: finalist with no_overlap=False (every signal traded).
IS: logged as a diagnostic trial.  VAL: one extra logged access under a distinct label; the
finalist was frozen and had already failed before this run, so no decision depends on it."""
import json
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import m1_is, gl, TRACK, side_stats, n_trials  # noqa: E402
from goldlab.evalkit import evaluate_is  # noqa: E402
from strategy import FINALISTS, make_orders  # noqa: E402

name = "meanrev-A-failedbreak-D5"
p = FINALISTS[name]
m1 = m1_is()
o = make_orders(m1, **p)
t, rep, rs = evaluate_is(m1, o, no_overlap=False)
t_is = gl.cut(t, "is")
gl.log_trial(TRACK, dict(p, no_overlap=False, _stage="diag", _note="overlap-allowed diagnostic of finalist A (coordinator request)"),
             dict(rep, stress_pf=rs["pf"], by_year=json.dumps(rep["by_year_R"]), **side_stats(t_is)))
print("trials:", n_trials())
keys = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "pf", "t_stat", "years_pos", "max_dd_R", "worst_week_R", "long_n", "long_R", "short_n", "short_R")
print("IS overlap-allowed:", json.dumps({k: rep[k] for k in keys}), "stress PF", rs["pf"], side_stats(t_is), rep["by_year_R"])
# max simultaneous positions
ev_ = sorted([(x, 1) for x in t_is.entry_time] + [(x, -1) for x in t_is.exit_time])
cur = mx = 0
for _, d in ev_:
    cur += d; mx = max(mx, cur)
print("max concurrent positions IS:", mx)
# VAL (distinct label, logged)
full = gl.load_m1("xauusd")
tv_all = gl.simulate(full, make_orders(full, **p), sym="xauusd", no_overlap=False)
tv = gl.cut(tv_all, "val", track=TRACK, label=name + "__overlap_diag")
rv = gl.report(tv)
print("VAL overlap-allowed:", json.dumps({k: rv[k] for k in keys}), side_stats(tv), rv["by_year_R"])
out = {"is": {k: rep[k] for k in keys}, "is_stress_pf": rs["pf"], "is_side": side_stats(t_is), "is_by_year": rep["by_year_R"],
       "is_max_concurrent": mx, "val": {k: rv[k] for k in keys}, "val_side": side_stats(tv), "val_by_year": rv["by_year_R"]}
json.dump(out, open(os.path.join(HERE, "..", "..", "results", "meanrev", "overlap_diag_A.json"), "w"), indent=1, default=str)
