"""S0: ref_lab.py reproduces results/r2/recalc/trades for the ten sleeves on the official in-sample frames, and builds
the references of the three kept changes from the lab's own implementations.

    python3 -I lab/robot/check/test_s0_refs.py

Runs check/ref_lab.py (official frames, every sleeve and the three changes, one fresh process each) and checks:
  * every sleeve: every official trade with entry and exit before 2022 identical (times, side, reason, prices, pnl, R);
    only trades whose official exit falls in 2022 may differ; NQB ran with set_leader (the default loader never ran);
  * the script files hold one row per lab order inside the frame;
  * K1 (BKE): the folds skip the high side with T(2019) 505.853, T(2020) 496.746, T(2021) 465.118 bp (SPEC 3, 0.001 bp),
    518 signals skipped; 2018-02..2021: 511 trades without the skip, 420 with it; no 3-spread refusal;
  * S0.75r (BKB): 563 trades in 2018-02..2021, no refusal;   H2 (F1E): 463 trades in 2018-02..2021, 100 held, no refusal.
"""
import json
import os
import subprocess
import sys

import pandas as pd

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "ref", "official")
W = pd.Timestamp("2018-02-01", tz="UTC")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
           NUMBA_CACHE_DIR=os.environ.get("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"))
K1_T = {"2019": 505.853, "2020": 496.746, "2021": 465.118}


def window(path):
    t = pd.read_parquet(path)
    return int((t.entry_time >= W).sum())


def main():
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ref_lab.py"), "--jobs", "4"], capture_output=True, text=True, env=ENV)
    print(r.stdout[-4000:])
    s = json.load(open(os.path.join(OUT, "summary.json")))
    res = {"ref_lab_exit": r.returncode, "sleeves": {}, "changes": {}}
    ok = r.returncode == 0
    for x in s["results"]:
        if "error" in x:
            ok = False
            res.setdefault("errors", []).append(x)
            continue
        if "change" in x:
            continue
        o = x["official"]
        good = o["pass"] and o["identical"] + len(o["differ_allowed_exit_in_2022_or_frame_end"]) == o["official_trades_before_2022"] \
            and x["script_rows"] + x["orders_beyond_frame"] == x["orders"]
        if x["code"] == "NQB":
            good &= "default loader never ran" in x.get("leader", "")
        res["sleeves"][x["code"]] = {"official": o["official_trades_before_2022"], "identical": o["identical"],
                                     "exit_in_2022": len(o["differ_allowed_exit_in_2022_or_frame_end"]), "pass": bool(good)}
        ok &= good
    ch = {x["change"]: x for x in s["results"] if "change" in x}
    k1 = ch["K1"]
    t_ok = all(abs(float(k1["folds"][y]["q_hi"]) - v) <= 1e-3 and k1["folds"][y]["skip"] == "hi" for y, v in K1_T.items())
    k1_w, k1_b = window(os.path.join(OUT, "changes", "K1", "trades.parquet")), window(os.path.join(OUT, "changes", "K1", "base.parquet"))
    res["changes"]["K1"] = {"folds": k1["folds"], "k1t_input": k1["k1t_input"], "skipped": k1["skipped"], "window_without": k1_b,
                            "window_with": k1_w, "refused": k1["refused_3spreads"],
                            "pass": t_ok and k1["skipped"] == 518 and k1_b == 511 and k1_w == 420 and k1["refused_3spreads"] == 0}
    s_w = window(os.path.join(OUT, "changes", "S0.75r", "trades.parquet"))
    res["changes"]["S0.75r"] = {"window": s_w, "refused": ch["S0.75r"]["refused_3spreads"],
                                "pass": s_w == 563 and ch["S0.75r"]["refused_3spreads"] == 0}
    h_w = window(os.path.join(OUT, "changes", "H2", "trades.parquet"))
    res["changes"]["H2"] = {"window": h_w, "held_trades": ch["H2"]["held_trades"], "refused": ch["H2"]["refused_3spreads"],
                            "pass": h_w == 463 and ch["H2"]["held_trades"] == 100 and ch["H2"]["refused_3spreads"] == 0}
    ok &= all(v["pass"] for v in res["changes"].values())
    res["pass"] = bool(ok)
    print(json.dumps(res, indent=1, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
