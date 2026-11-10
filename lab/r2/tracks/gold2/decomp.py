"""Diagnostic (in-sample trades, no new configuration): where does each candidate's profit come from,
relative to the legacy 4h sleeve?
  A  entered within +-4h of a legacy ENTRY on the same side (the same 10-day breakout)
  B  entered while a same-side legacy trade is open, but not within 4h of its entry (later in the move)
  C  everything else (legacy flat or opposite): the part that is independent of the legacy sleeve"""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, is_trades, pf, tstat
import stageA, stageB, stageD

LEG = stageA.A["A0_ref_legacy_donch4h_stop"][0]
CFG = {
    "SQ_1h": stageD.SQ, "SQ_2h": {**stageD.SQ, **stageD.CTRL["SQ"]["ctrl_2h_bars"]},
    "TR_1h": stageD.TR, "TR_2h": {**stageD.TR, **stageD.CTRL["TR"]["ctrl_2h_bars"]},
    "B1_d1h_n120_k3": stageB.B["B1_d1h_n120_k3"],
    "A5_orb_asia_2d_buf10": stageA.A["A5_orb_asia_2d_buf10"][0],
    "A1_orb_asia_intraday": stageA.A["A1_orb_asia_00-07ldn"][0],
}


def groups(t, leg, win_h=4):
    le = leg.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
    lx = leg.exit_time.to_numpy("datetime64[ns]").astype(np.int64)
    ls = leg.side.to_numpy()
    te = t.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
    sd = t.side.to_numpy()
    k = np.searchsorted(le, te, side="right") - 1
    kc = np.clip(k, 0, None)
    inside_same = (k >= 0) & (lx[kc] > te) & (ls[kc] == sd)
    kn = np.clip(k + 1, 0, len(le) - 1)
    w = win_h * 3600e9
    near_prev = (k >= 0) & (te - le[kc] <= w) & (ls[kc] == sd)
    near_next = (le[kn] - te <= w) & (le[kn] >= te) & (ls[kn] == sd)
    A = near_prev | near_next
    B = inside_same & ~A
    C = ~A & ~B
    return A, B, C


def stat(R):
    if len(R) == 0:
        return {"n": 0}
    return {"n": int(len(R)), "sum_R": round(float(R.sum()), 1), "exp_R": round(float(R.mean()), 4),
            "pf": round(pf(R), 3), "t": round(tstat(R), 2) if len(R) > 2 else None}


if __name__ == "__main__":
    leg = is_trades("xauusd", LEG)
    out = {}
    for name, p in CFG.items():
        t = is_trades("xauusd", p)
        A, B, C = groups(t, leg)
        R = t.R.to_numpy()
        out[name] = {"all": stat(R), "A_same_breakout_as_legacy": stat(R[A]), "B_later_inside_legacy_trade": stat(R[B]),
                     "C_independent_of_legacy": stat(R[C])}
        yrs = t.entry_time.dt.year.to_numpy()
        out[name]["C_by_year_R"] = {int(y): round(float(R[C & (yrs == y)].sum()), 1) for y in np.unique(yrs)}
        print(name, json.dumps(out[name]), flush=True)
    json.dump(out, open(os.path.join(RES, "decomposition_vs_legacy_is.json"), "w"), indent=1)
