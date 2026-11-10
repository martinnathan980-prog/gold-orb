import sys, time, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
OUT = "/home/user/gold-orb/lab/results/r2/leadlag/descriptive"
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
jobs = [
 ("us100","us500", {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}, "2014-01-01"),
 ("us100","us30",  {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}, "2014-01-01"),
 ("us500","us30",  {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}, "2014-01-01"),
 ("us500","us100", {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}, "2014-01-01"),
 ("us30","us100",  {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}, "2014-01-01"),
 ("us30","us500",  {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}, "2014-01-01"),
]
allr = []
for L, F, sess, st in jobs:
    t = time.time()
    r = desc.study(L, F, sess, start=st)
    allr.append(r)
    r.to_csv(os.path.join(OUT, f"{L}_to_{F}.csv"), index=False)
    cols = ["sess","pred","k","h","n","slope","t_slope","n_1%","days_1%","absx_1%","fwd_1%","t_1%","gap_1%","cost_1%","n_0.1%","days_0.1%","absx_0.1%","fwd_0.1%","t_0.1%","gap_0.1%","cost_0.1%"]
    print(f"=== {L} -> {F}  ({time.time()-t:.0f}s)")
    print(r[cols].to_string(index=False))
    sys.stdout.flush()
