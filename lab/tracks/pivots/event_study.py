"""Cost-free event study (IS only): do pivot levels make price react differently than random levels?

FADE event : first touch of a level in the day (armed at 18:00 NY = day open, level below the
             price = support / above = resistance).  Race from the level: +X in the bounce
             direction before -X through the level?  (touch bar: only the adverse side counts,
             conservative and identical for real and placebo levels).
BREAK event: first M15 bid close beyond the level.  Race from the next M1 open: +X further
             in the break direction before -X back?
X in {0.15, 0.25, 0.40} x daily ATR; races end at 16:00 NY (unresolved = dropped).
PLACEBO    : the same day's level set shifted by +-U(0.2,0.4) x ATR (random sign per day),
             20 seeds; round-number grids shifted by a random phase U(0.2,0.8) x grid.
Statistic  : success rate p = success / (success + failure); z = (p_real - mean p_placebo) /
             sd p_placebo across seeds.
"""
import json
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy as S  # noqa: E402
import goldlab as gl  # noqa: E402

OUT = os.path.join(S._LAB, "results", "pivots")
XS = (0.15, 0.25, 0.40)
NSEED = 20
WIN = ("NY", -360, "NY", 900)       # 18:00 NY (previous calendar day) -> 15:00 NY
EOD = 960                           # races resolved until 16:00 NY


@nb.njit(cache=True)
def _race(bh, bl, ref, start, end, dirn, X, adverse_first):
    n = len(ref)
    out = np.zeros(n, np.int8)
    for q in range(n):
        r = ref[q]
        d = dirn[q]
        x = X[q]
        i = start[q]
        b = end[q]
        up_l = r + x
        dn_l = r - x
        if adverse_first:
            if d > 0 and bl[i] <= dn_l:
                out[q] = -1
                continue
            if d < 0 and bh[i] >= up_l:
                out[q] = -1
                continue
            i += 1
        while i < b:
            up = bh[i] >= up_l
            dn = bl[i] <= dn_l
            if up and dn:
                out[q] = 2
                break
            if up:
                out[q] = 1 if d > 0 else -1
                break
            if dn:
                out[q] = -1 if d > 0 else 1
                break
            i += 1
    return out


def events(c, lv, mode, ws, we, ex, isday, last15):
    if mode == "fade":
        role, hit = S._first_touch(c["bl"], c["bh"], c["bo"], ws, we, lv)
    else:
        role, hit = S._first_close_beyond(c["bc"], last15, c["bo"], ws, we, lv)
    hit = np.where(isday[:, None], hit, -1)
    kk, jj = np.nonzero(hit >= 0)
    i = hit[kk, jj]
    r = role[kk, jj].astype(np.int64)
    if mode == "fade":
        dirn, ref, start, adv = r, lv[kk, jj], i, True
    else:
        dirn, ref, start, adv = -r, c["bo"][np.minimum(i + 1, c["N"] - 1)], i + 1, False
    ok = start < ex[kk]
    return dict(k=kk[ok], j=jj[ok], i=i[ok], dirn=dirn[ok], ref=ref[ok], start=start[ok],
                end=ex[kk[ok]], adv=adv)


def rates(c, ev, atr):
    out = {}
    for x in XS:
        X = x * atr[ev["k"]]
        o = _race(c["bh"], c["bl"], ev["ref"], ev["start"], ev["end"], ev["dirn"], X, ev["adv"])
        s, f = (o == 1).sum(), (o == -1).sum()
        out[x] = (s / max(s + f, 1), int(s + f), o)
    return out


def session_of(c, i):
    ldn, ny = c["tdmin_LDN"][i], c["tdmin_NY"][i]
    return np.where(ldn < 420, "asia", np.where(ny < 480, "london", "ny"))


def main():
    m1 = gl.load_m1("xauusd", end="2022-01-01")
    c = S.context(m1)
    D = c["D"]
    isday = ((D.index >= "2013-01-01") & (D.index < "2022-01-01") & D.full).to_numpy() & np.isfinite(D.atr.to_numpy())
    atr = D.atr.to_numpy()
    ws, we, ex = S.window_indices(c, WIN, EOD)
    last15 = S._bar_last_flags(c, 15)
    fams = [("floor", None), ("cam", None), ("pdhl", None), ("wfloor", None), ("round", 50.0), ("round", 10.0)]
    rows, detail = [], {}
    for fam, grid in fams:
        name = fam if grid is None else f"round{int(grid)}"
        if fam == "round":
            names = S.FAMILIES["round"]
            real = S._round_levels(c, ws, grid)
            pls = []
            for sd in range(NSEED):
                ph = np.random.default_rng(1000 + sd).uniform(0.2, 0.8, len(D)) * grid
                pls.append(S._round_levels(c, ws, grid, ph))
        else:
            names, real = S.family_levels(c, fam)
            pls = [real + S._placebo_shift(c, 1000 + sd)[:, None] for sd in range(NSEED)]
        for mode in ("fade", "break"):
            ev = events(c, np.ascontiguousarray(real), mode, ws, we, ex, isday, last15)
            rr = rates(c, ev, atr)
            pl = []
            pl_lvl = []
            for lvp in pls:
                evp = events(c, np.ascontiguousarray(lvp), mode, ws, we, ex, isday, last15)
                rp = rates(c, evp, atr)
                pl.append({x: rp[x][0] for x in XS})
                # per-level placebo rate at X=0.25
                o = rp[0.25][2]
                d = {}
                for j, nm in enumerate(names):
                    m = evp["j"] == j
                    s, f = ((o == 1) & m).sum(), ((o == -1) & m).sum()
                    d[nm] = s / max(s + f, 1)
                pl_lvl.append(d)
            res = {"family": name, "mode": mode, "n_events": int(len(ev["k"]))}
            for x in XS:
                pv = np.array([q[x] for q in pl])
                res[f"p_real_{x}"] = round(float(rr[x][0]), 4)
                res[f"n_res_{x}"] = rr[x][1]
                res[f"p_plac_{x}"] = round(float(pv.mean()), 4)
                res[f"sd_plac_{x}"] = round(float(pv.std(ddof=1)), 4)
                res[f"z_{x}"] = round(float((rr[x][0] - pv.mean()) / pv.std(ddof=1)), 2)
            # per level / session / role at X = 0.25 (real), with placebo per-level means
            o = rr[0.25][2]
            sess = session_of(c, ev["i"])
            per = {}
            for j, nm in enumerate(names):
                m = ev["j"] == j
                s, f = ((o == 1) & m).sum(), ((o == -1) & m).sum()
                plv = np.array([d[nm] for d in pl_lvl])
                per[nm] = {"n": int(s + f), "p": round(float(s / max(s + f, 1)), 4),
                           "p_plac": round(float(plv.mean()), 4), "sd_plac": round(float(plv.std(ddof=1)), 4)}
            bys = {}
            for ss in ("asia", "london", "ny"):
                m = sess == ss
                s, f = ((o == 1) & m).sum(), ((o == -1) & m).sum()
                bys[ss] = {"n": int(s + f), "p": round(float(s / max(s + f, 1)), 4)}
            byrole = {}
            for rname, rv in (("support/up", 1), ("resist/down", -1)):
                m = ev["dirn"] == rv
                s, f = ((o == 1) & m).sum(), ((o == -1) & m).sum()
                byrole[rname] = {"n": int(s + f), "p": round(float(s / max(s + f, 1)), 4)}
            res["per_level_0.25"] = per
            res["by_session_0.25"] = bys
            res["by_dir_0.25"] = byrole
            rows.append(res)
            print(json.dumps({k: v for k, v in res.items() if not k.startswith(("per_", "by_"))}))
            print("   per level:", json.dumps(per))
            print("   by session:", json.dumps(bys), " by dir:", json.dumps(byrole))
            gl.log_trial("pivots", {"kind": "event_study", "family": name, "mode": mode,
                                    "X_atr": list(XS), "win": "18:00NY-15:00NY first touch/close",
                                    "placebo_seeds": NSEED},
                         {k: v for k, v in res.items() if not k.startswith(("per_", "by_"))})
    with open(os.path.join(OUT, "event_study.json"), "w") as f:
        json.dump(rows, f, indent=1, default=str)


if __name__ == "__main__":
    main()
