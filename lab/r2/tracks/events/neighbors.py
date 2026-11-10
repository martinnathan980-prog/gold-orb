"""Neighbour robustness (IS): each tuned parameter moved to about +/-20% or to the adjacent sensible value."""
import json, sys
import numpy as np
from runner import trial, RES

PREM = dict(rule="long", lead=5, exit="hold", hold=15, stop_atr=1.0, atr_n=14)
PREM_NB = [("lead", 4), ("lead", 6), ("lead", 3), ("lead", 10), ("hold", 12), ("hold", 18), ("hold", 10), ("hold", 20),
           ("stop_atr", 0.8), ("stop_atr", 1.2), ("atr_n", 11), ("atr_n", 17)]
MOM = dict(rule="mom", kinds="fomc", k=5, exit="hhmm", exit_hhmm="15:55", exit_days=1, stop_atr=0.5, atr_n=14)
MOM_NB = [("k", 4), ("k", 6), ("k", 3), ("k", 10), ("stop_atr", 0.4), ("stop_atr", 0.6), ("atr_n", 11), ("atr_n", 17),
          ("exit_hhmm", "15:00"), ("exit_hhmm", "16:45")]
which = sys.argv[1]
out = {}
if which == "prem":
    for sym in ("us500", "us100"):
        pfs = {}
        for k, v in PREM_NB:
            p = dict(PREM); p[k] = v
            ev = trial(sym, p, tag=f"N:prem {k}={v}")
            pfs[f"{k}={v}"] = ev["is"]["pf"]
        out[sym] = {"neighbors": pfs, "median_pf_pm20": float(np.median([pfs[f"{k}={v}"] for k, v in PREM_NB if (k, v) not in (("lead", 3), ("lead", 10), ("hold", 10), ("hold", 20))])),
                    "median_pf_all": float(np.median(list(pfs.values())))}
        print(sym, out[sym], flush=True)
else:
    sym = "xauusd"
    trial(sym, MOM, full=True, tag="F:mom-full")
    pfs = {}
    for k, v in MOM_NB:
        p = dict(MOM); p[k] = v
        ev = trial(sym, p, tag=f"N:mom {k}={v}")
        pfs[f"{k}={v}"] = ev["is"]["pf"]
    out[sym] = {"neighbors": pfs, "median_pf_pm20": float(np.median([pfs[f"{k}={v}"] for k, v in MOM_NB if (k, v) not in (("k", 3), ("k", 10))])),
                "median_pf_all": float(np.median(list(pfs.values())))}
    print(sym, out[sym], flush=True)
json.dump(out, open(f"{RES}/neighbors_{which}.json", "w"), indent=1)
