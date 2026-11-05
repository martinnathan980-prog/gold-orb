"""Event study, part 2 (IS only): same tests as event_study.py but in the ACTIVE window
(armed at 08:00 London, touches until 12:00 NY, races until 16:00 NY) -- the window a
London/NY discretionary trader would use -- with the placebo comparison done per session
(London 08:00 LDN-08:00 NY, NY 08:00-12:00 NY) and per level.  Families: floor, pdhl,
round50, round10 (cam / weekly showed nothing in part 1)."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy as S
import goldlab as gl
from event_study import _race, events, XS, NSEED, OUT

WIN = ("LDN", 480, "NY", 720)
EOD = 960


def main():
    m1 = gl.load_m1("xauusd", end="2022-01-01")
    c = S.context(m1)
    D = c["D"]
    atr = D.atr.to_numpy()
    isday = ((D.index >= "2013-01-01") & (D.index < "2022-01-01") & D.full).to_numpy() & np.isfinite(atr)
    ws, we, ex = S.window_indices(c, WIN, EOD)
    last15 = S._bar_last_flags(c, 15)
    rows = []
    for fam, grid in (("floor", None), ("pdhl", None), ("round", 50.0), ("round", 10.0)):
        name = fam if grid is None else f"round{int(grid)}"
        if fam == "round":
            names = S.FAMILIES["round"]
            real = S._round_levels(c, ws, grid)
            pls = [S._round_levels(c, ws, grid, np.random.default_rng(1000 + sd).uniform(0.2, 0.8, len(D)) * grid)
                   for sd in range(NSEED)]
        else:
            names, real = S.family_levels(c, fam)
            pls = [real + S._placebo_shift(c, 1000 + sd)[:, None] for sd in range(NSEED)]
        for mode in ("fade", "break"):
            def stats(lv):
                ev = events(c, np.ascontiguousarray(lv), mode, ws, we, ex, isday, last15)
                ny = c["tdmin_NY"][ev["i"]] >= 480
                res = {}
                for x in XS:
                    o = _race(c["bh"], c["bl"], ev["ref"], ev["start"], ev["end"], ev["dirn"], x * atr[ev["k"]], ev["adv"])
                    groups = {"all": np.ones(len(o), bool), "london": ~ny, "ny": ny}
                    if x == 0.25:
                        for j, nm in enumerate(names):
                            groups[nm] = ev["j"] == j
                    for g, m in groups.items():
                        s, f = ((o == 1) & m).sum(), ((o == -1) & m).sum()
                        res[(x, g)] = (s / max(s + f, 1), int(s + f))
                return res
            r = stats(real)
            P = [stats(lv) for lv in pls]
            out = {"family": name, "mode": mode}
            line = []
            for key in r:
                pv = np.array([q[key][0] for q in P])
                z = (r[key][0] - pv.mean()) / pv.std(ddof=1)
                out[f"{key[1]}@{key[0]}"] = {"n": r[key][1], "p": round(float(r[key][0]), 4),
                                             "p_plac": round(float(pv.mean()), 4), "z": round(float(z), 2)}
                line.append(f"{key[1]}@{key[0]}: n={r[key][1]} p={r[key][0]:.3f} plac={pv.mean():.3f} z={z:+.2f}")
            print(f"== {name} {mode}")
            for l in line:
                print("   ", l)
            rows.append(out)
            gl.log_trial("pivots", {"kind": "event_study_active", "family": name, "mode": mode,
                                    "X_atr": list(XS), "win": "08:00LDN-12:00NY first touch/close",
                                    "placebo_seeds": NSEED},
                         {"n": out["all@0.25"]["n"], "p_real_0.25": out["all@0.25"]["p"],
                          "p_plac_0.25": out["all@0.25"]["p_plac"], "z_0.25": out["all@0.25"]["z"],
                          "z_0.15": out["all@0.15"]["z"], "z_0.4": out["all@0.4"]["z"]})
    with open(os.path.join(OUT, "event_study_active.json"), "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
