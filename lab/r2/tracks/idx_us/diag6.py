"""IS-only: first-minute continuation after an n-minute opening candle (own sign, big candles), n = 1..12, and the
rest-of-day continuation measured from one minute later (i.e. what an entry one minute late would still capture)."""
from harness import *     # noqa
import idxus_lib as cm
bpf = lambda a, b: (b / a - 1) * 1e4
def ts(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return (round(float(x.mean()), 2), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2))
for sym in ("us100", "us500", "us30"):
    m1 = r2.load(sym, start="2013-06-01", end="2022-01-01")
    g = cm.grid(m1)
    P, O, half, dts = g["P"], g["O"], g["half"], g["dates"]
    ok = (~half) & np.array([d >= S.MIN_DATE for d in dts])
    print("=====", sym, " n: (first minute after signal bp,t) | (signal+1min -> 15:55 bp,t) | (signal -> 15:55 bp,t)   [big candles: >= trailing median]")
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30):
        mv = P[:, n] / O - 1; s = np.sign(mv); am = np.abs(mv)
        med = pd.Series(am).rolling(20, min_periods=10).median().shift(1).to_numpy()
        big = ok & np.isfinite(med) & (am >= med) & (s != 0)
        print(f"   n={n:>2} N={int(big.sum())}", ts((s * bpf(P[:, n], P[:, n + 1]))[big]), "|", ts((s * bpf(P[:, n + 1], P[:, 385]))[big]), "|", ts((s * bpf(P[:, n], P[:, 385]))[big]))
    r2.free()
