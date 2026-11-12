"""Data availability of the in-sample frames on the sessions of the list (no rule result is computed here), and the
declared drop rule of configuration (6) (declared.json R19): (6) is dropped only if fewer than 50 % of the sessions
have an us100 bar AND an us30 bar starting in [16:00, 16:10) New York.
Writes results/r2/round4/letf_close_pair/data_check.json. Run after declare.py and before run.py."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

COLS = {"15:29": 29, "15:30": 30, "15:40": 40, "15:57": 57, "15:59": 59, "16:05": 65}


def main():
    fr = C.load_frames()
    out = {"frames": {}}
    for s, df in fr.items():
        sec = (df.index.as_unit("ns").asi8 % C.MIN_NS)
        out["frames"][s] = {"rows_read": int(len(df)), "first": str(df.index[0]), "last": str(df.index[-1]),
                            "max_ts_lt_2022": bool(df.index.max() < C.CUT), "non_whole_minute_stamps": int((sec != 0).sum())}
    cal = C.calendar()
    P = C.prepare(C.build_grid(fr, cal["tdays"]))
    del fr
    rows, prow = cal["srow"], cal["prev_row"]
    have = np.isfinite(P["mo"])                                          # (3, R, NMIN) exact bars
    yrs = cal["sessions"].year.to_numpy()
    after16 = have[:, rows, 60:70].any(axis=2)                           # a bar starting in [16:00, 16:10)
    by = {}
    for y in np.unique(yrs):
        m = yrs == y
        row = {"sessions": int(m.sum()), "sessions_after_an_early_close": int(cal["prev_half"][m].sum())}
        for i, s in enumerate(C.SYMS):
            hv = have[i][rows[m]]
            row[s] = {k: int(hv[:, c].sum()) for k, c in COLS.items()}
            row[s]["prev_session_15:59"] = int(have[i][prow[m], 59].sum())
            row[s]["bar_in_16:00-16:10"] = int(after16[i][m].sum())
            sp = (P["ao"][i][rows[m]] - P["bo"][i][rows[m]]) / P["mo"][i][rows[m]] * 1e4
            for k in ("15:30", "15:59", "16:05"):
                row[s][f"median_spread_bp_{k}"] = round(float(np.nanmedian(sp[:, COLS[k]])), 3) if np.isfinite(sp[:, COLS[k]]).any() else None
        row["us100_and_us30_bar_in_16:00-16:10"] = int((after16[0][m] & after16[1][m]).sum())
        by[int(y)] = row
    out["by_year"] = by
    both = after16[0] & after16[1]
    share = float(both.mean())
    out["sessions_total"] = int(len(rows))
    out["first_session"], out["last_session"] = str(cal["sessions"][0].date()), str(cal["sessions"][-1].date())
    out["sessions_after_an_early_close_total"] = int(cal["prev_half"].sum())
    out["R19_drop_rule_of_6"] = {"share_of_sessions_with_us100_and_us30_bar_in_16:00-16:10": round(share, 4),
                                 "threshold": 0.5, "config_6_dropped": bool(share < 0.5)}
    C.jdump(out, os.path.join(C.OUT, "data_check.json"))
    for y, r in by.items():
        print(y, r["sessions"], "after-early-close", r["sessions_after_an_early_close"],
              {s: (r[s]["15:29"], r[s]["15:30"], r[s]["15:59"], r[s]["prev_session_15:59"], r[s]["bar_in_16:00-16:10"],
                   r[s]["median_spread_bp_15:30"], r[s]["median_spread_bp_16:05"]) for s in C.SYMS})
    print(out["frames"])
    print(out["R19_drop_rule_of_6"])


if __name__ == "__main__":
    main()
