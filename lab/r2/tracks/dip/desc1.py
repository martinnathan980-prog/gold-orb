"""Descriptive (not a trial): next-session return (entry bar open at the cash close -> entry bar open at the
next tradable cash close, mid prices, no cost) by signal bucket, IS 2014-2021 only, data loaded to 2021-12-31."""
import numpy as np, pandas as pd
from common import *
out = []
lines = []
for sym in ["us500", "us100", "us30", "ger40"]:
    use(sym)
    m1 = r2.load(sym, end="2022-01-01")
    s = S.sessions(m1, SESS[sym])
    mid = (m1.bo.to_numpy() + m1.ao.to_numpy()) / 2
    t = s[s.tradable].copy()
    px = mid[t.entry_i.to_numpy()]
    t["r1"] = (np.r_[px[1:], np.nan] / px - 1) * 1e4       # next tradable close, bp
    gap = np.busday_count(t.index.to_numpy()[:-1].astype("datetime64[D]"), t.index.to_numpy()[1:].astype("datetime64[D]"))
    t["gapd"] = np.r_[gap, 9]
    ibs = ((s.c - s.l) / (s.h - s.l)).reindex(t.index)
    rsi = S._rsi(s.c, 2).reindex(t.index)
    t = t[(t.index >= "2014-01-01") & (t.gapd <= 3)]
    ibs, rsi = ibs.reindex(t.index), rsi.reindex(t.index)
    sig = {f"ibs<0.2": ibs < 0.2, "ibs0.2-0.4": (ibs >= .2) & (ibs < .4), "ibs0.4-0.6": (ibs >= .4) & (ibs < .6),
           "ibs0.6-0.8": (ibs >= .6) & (ibs < .8), "ibs>0.8": ibs >= .8,
           "rsi2<10": rsi < 10, "rsi2>90": rsi > 90}
    for side in (1, -1):
        sig[f"down3" if side > 0 else "up3"] = pd.Series(S.signals(s, "down3", 3, side), index=s.index).reindex(t.index)
        sig["bb_low" if side > 0 else "bb_up"] = pd.Series(S.signals(s, "bb", 0, side), index=s.index).reindex(t.index)
    sig["all"] = pd.Series(True, index=t.index)
    lines.append(f"\n{sym}: tradable IS sessions 2014-2021 = {len(t)}   (per year: {t.groupby(t.index.year).size().to_dict()})")
    lines.append(f"{'bucket':<12} {'n':>5} {'mean bp':>8} {'t':>6} {'win%':>6} | {'n1':>4} {'bp 14-17':>8} | {'n2':>4} {'bp 18-21':>8}")
    for k, m in sig.items():
        r = t.r1[m.to_numpy(bool)].dropna()
        h1, h2 = r[r.index < "2018-01-01"], r[r.index >= "2018-01-01"]
        tt = r.mean() / r.std() * np.sqrt(len(r))
        lines.append(f"{k:<12} {len(r):>5} {r.mean():>8.2f} {tt:>6.2f} {100*(r>0).mean():>6.1f} | {len(h1):>4} {h1.mean():>8.2f} | {len(h2):>4} {h2.mean():>8.2f}")
        out.append({"sym": sym, "bucket": k, "n": len(r), "bp": r.mean(), "t": tt, "bp_h1": h1.mean(), "bp_h2": h2.mean()})
    del m1
r2.free()
txt = "\n".join(lines) + f"\n\ncells looked at: {len([o for o in out if o['bucket']!='all'])} buckets x 3 (all / first half / second half)\n"
print(txt)
open(f"{RES}/desc1_next_session.txt", "w").write(txt)
pd.DataFrame(out).to_csv(f"{RES}/desc1_next_session.csv", index=False)
