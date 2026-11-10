"""IS-only: where does the edge sit in the first minutes after the signal?  (latency sensitivity)"""
from harness import *     # noqa
import idxus_lib as cm

def ts(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return (len(x), round(float(x.mean()), 2), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2))

bp = lambda a, b: (b / a - 1) * 1e4
for sym in ("us100", "us500"):
    m1 = r2.load(sym, start="2013-06-01", end="2022-01-01")
    g = cm.grid(m1)
    P, O, half = g["P"], g["O"], g["half"]
    dts = g["dates"]
    ok = (~half) & np.array([d >= S.MIN_DATE for d in dts])
    move = P[:, 5] / O - 1
    s = np.sign(move); am = np.abs(move)
    med = pd.Series(am).rolling(20, min_periods=10).median().shift(1).to_numpy()
    big = ok & np.isfinite(med) & (am >= med) & (s != 0)
    small = ok & np.isfinite(med) & (am < med) & (s != 0)
    print("=====", sym, "OCM: signed move after 09:35 (bp), big candles n=", int(big.sum()))
    print("  big  :", {f"+{k}m": ts((s * bp(P[:, 5], P[:, 5 + k]))[big]) for k in (1, 2, 3, 5, 10, 25, 55, 115, 235, 380)})
    print("  small:", {f"+{k}m": ts((s * bp(P[:, 5], P[:, 5 + k]))[small]) for k in (1, 2, 3, 5, 10, 25, 55, 115, 235, 380)})
    # where inside the first minute?  open of the 09:35 bar vs P5 (close of the 09:34 bar), and close of the 09:35 bar
    EI = g["EI"]
    mo = ((m1.bo.to_numpy() + m1.ao.to_numpy()) / 2)
    e = EI[:, 5]
    op35 = np.where(e >= 0, mo[np.clip(e, 0, len(mo) - 1)], np.nan)
    print("  big: P(09:35 known) -> OPEN of the 09:35 bar:", ts((s * bp(P[:, 5], op35))[big]), "| OPEN 09:35 bar -> P(09:36):", ts((s * bp(op35, P[:, 6]))[big]))
    # per-minute profile inside the candle and after: sign defined at 09:35, minute returns from 09:30
    prof = {f"{570 + k}": ts((s * bp(P[:, k], P[:, k + 1]))[big])[1] for k in range(0, 15)}
    print("  big: per-minute signed returns, minutes 09:30..09:44 (first 5 are inside the candle):", prof)
    # one-minute abs return scale at 09:35
    print("  median |1-min return| 09:35-09:36 (bp):", round(float(np.nanmedian(np.abs(bp(P[:, 5], P[:, 6]))[ok])), 2))
    # noise rule: signed 1-minute move after the check, for breaches at the checks
    checks = np.arange(30, 361, 30)
    absmove = np.abs(P[:, checks] / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(14, min_periods=9).mean().shift(1).to_numpy()
    cl = P[:, 390]; pc = np.r_[np.nan, cl[:-1]]
    hi = np.where(np.isfinite(pc), np.fmax(O, pc), O); lo = np.where(np.isfinite(pc), np.fmin(O, pc), O)
    out = {}
    for j, m in enumerate(checks):
        p = P[:, m]
        up = ok & (p > hi * (1 + sig[:, j])); dn = ok & (p < lo * (1 - sig[:, j]))
        sd = np.where(up, 1, np.where(dn, -1, 0))
        w = sd != 0
        out[f"{(570 + m) // 60:02d}:{(570 + m) % 60:02d}"] = (ts((sd * bp(P[:, m], P[:, m + 1]))[w]), ts((sd * bp(P[:, m], P[:, min(m + 5, 390)]))[w]), ts((sd * bp(P[:, m], P[:, min(m + 29, 390)]))[w]))
    print("  NOISE: outside band at check -> signed move over next 1 / 5 / 29 minutes (n, mean bp, t):")
    for k, v in out.items():
        print("     ", k, v)
    allw = []
    r2.free()
