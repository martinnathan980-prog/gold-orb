"""Diagnostic (in-sample trades only, no new configuration): how much do the stage-B candidates
duplicate the legacy 4h sleeve (and each other)?"""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, is_trades, pf, tstat
import stageA, stageB

LEG = stageA.A["A0_ref_legacy_donch4h_stop"][0]


def weekly(t):
    return t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()


def overlap_stats(t, leg):
    le = leg.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
    lx = leg.exit_time.to_numpy("datetime64[ns]").astype(np.int64)
    ls = leg.side.to_numpy()
    te = t.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
    k = np.searchsorted(le, te, side="right") - 1          # last legacy trade entered at/before this entry
    inside = (k >= 0) & (lx[np.clip(k, 0, None)] > te)
    same = inside & (ls[np.clip(k, 0, None)] == t.side.to_numpy())
    opp = inside & ~same
    # entered within 4h of a legacy entry on the same side (same breakout)
    kn = np.clip(np.searchsorted(le, te), 0, len(le) - 1)
    near = (np.minimum(np.abs(te - le[np.clip(k, 0, None)]), np.abs(le[kn] - te)) <= 4 * 3600e9)
    R = t.R.to_numpy()
    f = lambda m: {"share": round(float(m.mean()), 3), "n": int(m.sum()), "exp_R": round(float(R[m].mean()), 4) if m.any() else None,
                   "pf": round(pf(R[m]), 3) if m.any() else None, "t": round(tstat(R[m]), 2) if m.sum() > 2 else None}
    return {"legacy_open_same_side": f(same), "legacy_open_opposite": f(opp), "legacy_flat": f(~inside),
            "entry_within_4h_of_legacy_entry": f(near)}


if __name__ == "__main__":
    names = sys.argv[1:] or ["B1_d1h_n240_k2", "B1_d1h_n240_k3", "B1_d1h_n120_k2", "B1_d1h_n120_k3", "B3_d1h_n48_tr240_k2",
                             "B3_d1h_n120_tr480_k3", "B5_sq1h_n24_07", "B5_sq1h_n48_07"]
    leg = is_trades("xauusd", LEG)
    wl = weekly(leg)
    out = {}
    W = {"legacy": wl}
    for nm in names:
        t = is_trades("xauusd", stageB.B[nm])
        o = overlap_stats(t, leg)
        w = weekly(t)
        W[nm] = w
        al = pd.concat([wl, w], axis=1).fillna(0.0)
        o["weekly_R_corr_with_legacy"] = round(float(al.corr().iloc[0, 1]), 3)
        o["n"] = int(len(t)); o["exp_R"] = round(float(t.R.mean()), 4)
        out[nm] = o
        print(nm, json.dumps(o), flush=True)
    C = pd.concat(W, axis=1).fillna(0.0).corr().round(2)
    print(C.to_string())
    out["weekly_R_corr_matrix"] = C.to_dict()
    json.dump(out, open(os.path.join(RES, "overlap_with_legacy_is.json"), "w"), indent=1)
