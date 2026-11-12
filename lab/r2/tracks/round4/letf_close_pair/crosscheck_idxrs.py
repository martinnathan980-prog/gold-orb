"""Cross-check (declared.json R23 c): every pair of the main re-simulated with IDXRS_1000's two-leg simulator
(r2/tracks/round4/idxrs_1000/common.sim_pairs, imported READ-ONLY under another module name, on its own 09:30-16:00
grid built by its own code from the in-sample frames). IDXRS_1000's simulator always buys leg S (weight 1) and sells
leg W (weight h):
  d > 0: S = us100, W = us30, weight h, stop -1.5 sd_pi                 -> the same pair;
  d < 0: S = us30, W = us100, weight 1/h, stop -1.5 sd_pi / h           -> the same pair scaled by 1/h
         (its mark is pi / h, so the stop decision is identical and R = net' / (1.5 sd_pi / h) = net / (1.5 sd_pi)).
Writes results/r2/round4/letf_close_pair/crosscheck_idxrs.json."""
import hashlib
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

IDXRS = os.path.join(C.LAB, "r2", "tracks", "round4", "idxrs_1000", "common.py")


def main():
    sha = hashlib.sha256(open(IDXRS, "rb").read()).hexdigest()
    spec = importlib.util.spec_from_file_location("idxrs_common_readonly", IDXRS)
    X = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(X)
    days = X.sessions()
    fr = X.load_frames(1.0)                           # its own loader: parquet filter ts < 2022-01-01
    PX = X.prepare(X.build_grid(fr, days))
    del fr
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    pos = {d.date(): i for i, d in enumerate(days)}
    dates = t.entry_time.dt.tz_convert(C.NY).dt.date
    dd = np.array([pos[d] for d in dates], np.int64)
    up = t.dir.to_numpy() > 0
    iu, i30 = X.SYMS.index("us100"), X.SYMS.index("us30")
    S = np.where(up, iu, i30)
    W = np.where(up, i30, iu)
    h = t.h.to_numpy(float)
    sdpi = t.sd_pi.to_numpy(float)
    hp = np.where(up, h, 1.0 / h)
    sdp = np.where(up, sdpi, sdpi / h)
    e, x, k = 360, 389, 1.5                           # 15:30 and 15:59 on its 09:30-based grid
    r = X.sim_pairs(PX, dd, S, W, hp, sdp, e, x, k)
    R_x = r["net"] / (k * sdp)
    stop_x = r["stopped"]
    u_x = r["u"]
    out = {"idxrs_common_sha256": sha, "n_pairs": int(len(t)),
           "filled_all": bool(r["filled"].all()),
           "same_exit_reason": int((stop_x == (t.reason.to_numpy() == "stop")).sum()),
           "same_stop_decision_bar": int(((~stop_x & (t.reason.to_numpy() == "time"))
                                         | (stop_x & (u_x == t.stop_decision_col.to_numpy()))).sum()),
           "R_max_abs_diff": float(np.nanmax(np.abs(R_x - t.R.to_numpy()))),
           "R_equal_to_1e-9": int(np.isclose(R_x, t.R.to_numpy(), rtol=0, atol=1e-9).sum()),
           "mean_R_this_engine": round(float(t.R.mean()), 6), "mean_R_idxrs_engine": round(float(np.mean(R_x)), 6),
           "pf_this_engine": round(C.pf(t.R), 4), "pf_idxrs_engine": round(C.pf(R_x), 4),
           "idxrs_exit_fallback": int(r["fallback"].sum())}
    diff = np.flatnonzero(~np.isclose(R_x, t.R.to_numpy(), rtol=0, atol=1e-9))
    out["differing_pairs"] = [{"date": str(dates.iloc[i]), "dir": int(t.dir.iloc[i]), "R_this": float(t.R.iloc[i]),
                               "R_idxrs": float(R_x[i]), "reason_this": t.reason.iloc[i], "stop_idxrs": bool(stop_x[i])}
                              for i in diff[:20]]
    out["pass"] = bool(out["same_exit_reason"] == len(t) and out["same_stop_decision_bar"] == len(t)
                       and out["R_equal_to_1e-9"] == len(t))
    C.jdump(out, os.path.join(C.OUT, "crosscheck_idxrs.json"))
    print({kk: v for kk, v in out.items() if kk != "differing_pairs"})
    print(out["differing_pairs"])


if __name__ == "__main__":
    main()
