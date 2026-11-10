import sys, time, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
OUT = "/home/user/gold-orb/lab/results/r2/leadlag/descriptive"
os.makedirs(OUT, exist_ok=True)
S3 = {"uscash": desc.S_USCASH, "preus": desc.S_PREUS, "night": desc.S_NIGHT}
SD = {"xetra": desc.S_XETRA, "eurex_pm": desc.S_EUREX_PM, "daxoff": desc.S_DAXOFF, "eu_am": desc.S_EUAM}
SC = {"all": desc.S_ALL, "uscash": desc.S_USCASH}
jobs = [
 ("xauusd","xagusd", S3, "2013-01-01"),
 ("xagusd","xauusd", S3, "2013-01-01"),
 ("btcusd","ethusd", SC, "2018-01-01"),
 ("ethusd","btcusd", SC, "2018-01-01"),
 ("us500","ger40", SD, "2014-01-01"),
 ("ger40","us500", SD, "2014-01-01"),
 ("us100","btcusd", SC, "2017-06-01"),
 ("btcusd","us100", SC, "2017-06-01"),
]
for L, F, sess, st in jobs:
    t = time.time()
    r = desc.study(L, F, sess, start=st)
    r.to_csv(os.path.join(OUT, f"{L}_to_{F}.csv"), index=False)
    print(f"=== {L} -> {F}  ({time.time()-t:.0f}s)", flush=True)
