import sys, time, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500); pd.set_option("display.max_colwidth", 200)
S = {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT,
     "us_pm": lambda ny, be, wd: (ny >= 955) & (ny < 1020) & (wd < 5)}
OUT = "/home/user/gold-orb/lab/results/r2/leadlag/descriptive"
r = desc.study("us100", "btcusd", S, ks=(1,5,15), hs=(1,5,15,30,60,120), start="2017-06-01", years=True)
r.to_csv(os.path.join(OUT, "us100_to_btcusd_sessions_long_horizons.csv"), index=False)
r = r[r.pred == "lead"]
print(r[["sess","k","h","n_1%","days_1%","absx_1%","fwd_1%","t_1%","gap_1%","cost_1%","n_0.1%","fwd_0.1%","t_0.1%","by_year_1%"]].to_string(index=False))
