import sys, time, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500); pd.set_option("display.max_colwidth", 200)
SD = {"xetra": desc.S_XETRA, "eurex_pm": desc.S_EUREX_PM, "eu_am": desc.S_EUAM, "daxoff": desc.S_DAXOFF}
for L, F in (("ger40","ger40"), ("us500","us500")):
    r = desc.study(L, F, SD, ks=(1,5,15), hs=(1,5,15,30), start="2014-01-01", years=True)
    r = r[r.pred == "lead"]
    print(f"=== OWN return of {F}: sign(own k-min return) x forward return (negative = reversal)")
    print(r[["sess","k","h","n_1%","days_1%","absx_1%","fwd_1%","t_1%","gap_1%","cost_1%","n_0.1%","fwd_0.1%","t_0.1%","by_year_1%"]].to_string(index=False))
