import sys, time, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500); pd.set_option("display.max_colwidth", 200)
SC = {"all": desc.S_ALL, "uscash": desc.S_USCASH}
SD = {"xetra": desc.S_XETRA, "eurex_pm": desc.S_EUREX_PM, "eu_am": desc.S_EUAM}
jobs = [
 ("us100","btcusd", SC, "2017-06-01", (1,5,15), (5,15,30)),
 ("btcusd","ethusd", SC, "2018-01-01", (1,), (1,5,15)),
 ("ethusd","btcusd", SC, "2018-01-01", (1,), (1,5,15)),
 ("btcusd","btcusd", SC, "2017-06-01", (1,), (1,5,15)),
 ("ethusd","ethusd", SC, "2018-01-01", (1,), (1,5,15)),
 ("us500","ger40", SD, "2014-01-01", (1,5,15), (5,15,30)),
 ("ger40","us500", SD, "2014-01-01", (1,5,15), (15,30)),
]
for L, F, sess, st, ks, hs in jobs:
    r = desc.study(L, F, sess, ks=ks, hs=hs, start=st, years=True)
    print(f"=== {L} -> {F}")
    print(r[["sess","pred","k","h","n_1%","days_1%","absx_1%","fwd_1%","t_1%","cost_1%","by_year_1%"]].to_string(index=False))
    sys.stdout.flush()
