"""Rebuild the IN-SAMPLE-ONLY mid-price cache used by desc.py / desc_rs.py / desc_z.py (descriptive study).
Reads the FP research frames, cuts them at 2022-01-01 and stores mid open/close/high/low + spread (bp)."""
import gc
import os
import sys

import numpy as np
import pandas as pd

D = "/home/user/gold-orb/lab/data/fp"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/ll"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
os.makedirs(OUT, exist_ok=True)
for s in ["us100", "us500", "us30", "ger40", "xauusd", "xagusd", "btcusd", "ethusd"]:
    df = pd.read_parquet(os.path.join(D, f"{s}_m1.parquet"))
    df = df[df.index < IS_END]            # in-sample only
    idx = df.index
    np.savez(os.path.join(OUT, f"{s}_is.npz"), tmin=(idx.asi8 // 60000).astype(np.int64),
             mo=((df.bo + df.ao) / 2).to_numpy(), mc=((df.bc + df.ac) / 2).to_numpy(),
             mh=((df.bh + df.ah) / 2).to_numpy(), ml=((df.bl + df.al) / 2).to_numpy(),
             sp=((df.ac - df.bc) / ((df.ac + df.bc) / 2) * 1e4).to_numpy().astype(np.float32))
    print(s, len(df), idx[0], idx[-1], flush=True)
    del df
    gc.collect()
