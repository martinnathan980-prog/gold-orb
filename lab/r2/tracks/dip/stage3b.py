import json, numpy as np, pandas as pd
from common import *
from goldlab.split import cut
A = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="close", trend=False, exit="sma5", hold=5)
B = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="1830", trend=False, exit="time", hold=1)
out = {}
for nm, P, syms in (("A", A, ["us500", "us100", "us30", "ger40"]), ("B", B, ["us500", "us100", "us30"])):
    for sym in syms:
        ev = trial(sym, P, f"{nm} FULL", full=True)
        p = dict(P, sess=SESS[sym])
        nul = r2.null_test(sym, S.make_orders, p, mode="day")
        print("   null", nul, flush=True)
        t = cut(r2.run(sym, S.make_orders, p, "fp"), "is")
        tg = cut(r2.run(sym, S.make_orders, p, "gross"), "is")
        t[["entry_time", "exit_time", "side", "entry", "exit", "stop", "R", "pnl", "swap", "reason"]].assign(
            gross_bp=(tg.side * (tg.exit - tg.entry) / tg.entry * 1e4).reindex(t.index)).to_csv(f"{RES}/trades_{nm}_{sym}.csv")
        out[f"{nm}_{sym}"] = {"ev": ev, "null": nul}
    r2.free()
json.dump(out, open(f"{RES}/stage3_full.json", "w"), indent=1, default=str)
