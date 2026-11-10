"""Stage E - neighbour robustness of the two finalist candidates in their weekday-only form
(each tuned parameter at about +/-20 %)."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa

BRK = {"family": "brk", "n": 72, "stop_atr": 3.0, "hold_h": 24, "dow": "weekday"}
SESS = {"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 13, "dow": "weekday"}
NB = {
    "brk72_24h_wd": [dict(BRK, n=58), dict(BRK, n=86), dict(BRK, stop_atr=2.4), dict(BRK, stop_atr=3.6),
                     dict(BRK, hold_h=19), dict(BRK, hold_h=29)],
    "sess_8_8_13_wd": [dict(SESS, dec_h=7), dict(SESS, dec_h=9), dict(SESS, look_h=6), dict(SESS, look_h=10),
                       dict(SESS, hold_h=10), dict(SESS, hold_h=16), dict(SESS, stop_atr=2.4), dict(SESS, stop_atr=3.6)],
}

if __name__ == "__main__":
    out = {}
    for sym in ("btcusd", "ethusd"):
        for name, lst in NB.items():
            for p in lst:
                ev = run_trial(sym, p, full=False, stage="E-neighbor-wd", note=f"neighbour of {name}")
                out.setdefault(f"{name}:{sym}", []).append({"params": p, "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"],
                                                            "exp_R": ev["is"]["expectancy_R"], "n": ev["is"]["n"],
                                                            "years_pos": ev["is"]["years_pos"], "by_year_R": ev["is"]["by_year_R"]})
        r2.free()
    for k, v in out.items():
        pfs = sorted(x["pf"] for x in v)
        out[k] = {"neighbors": v, "pfs_sorted": pfs, "median_pf": float(np.median(pfs)), "min_pf": pfs[0]}
        print(k, "neighbour PFs", pfs, "median", float(np.median(pfs)))
    json.dump(out, open(os.path.join(OUT, "neighbors_weekday.json"), "w"), indent=1)
