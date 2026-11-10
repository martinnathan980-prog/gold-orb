"""IS-only: next-minute continuation when the price is outside the noise band, at EVERY minute of the day
(band computed for every minute offset), split by minute-of-hour.  Is the first-minute effect a clock-time effect?"""
from harness import *     # noqa
import idxus_lib as cm
bpf = lambda a, b: (b / a - 1) * 1e4
def ts(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return (len(x), round(float(x.mean()), 2), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)) if len(x) > 5 else (len(x), None, None)
for sym in ("us100", "us500"):
    m1 = r2.load(sym, start="2013-06-01", end="2022-01-01")
    g = cm.grid(m1)
    P, O, half, dts = g["P"], g["O"], g["half"], g["dates"]
    ok = (~half) & np.array([d >= S.MIN_DATE for d in dts])
    absmove = np.abs(P / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(14, min_periods=9).mean().shift(1).to_numpy()
    cl = P[:, 390]; pc = np.r_[np.nan, cl[:-1]]
    hi = np.where(np.isfinite(pc), np.fmax(O, pc), O); lo = np.where(np.isfinite(pc), np.fmin(O, pc), O)
    UB = hi[:, None] * (1 + sig); LB = lo[:, None] * (1 - sig)
    sd = np.where(P > UB, 1, np.where(P < LB, -1, 0)).astype(float)
    sd[~ok] = 0
    nxt1 = np.full_like(P, np.nan); nxt1[:, :-1] = bpf(P[:, :-1], P[:, 1:])
    prv1 = np.full_like(P, np.nan); prv1[:, 1:] = bpf(P[:, :-1], P[:, 1:])
    mins = np.arange(391)
    moh = (mins + 30) % 60
    sel = lambda cond: (sd != 0) & cond[None, :] & (mins[None, :] >= 30) & (mins[None, :] <= 388)
    print("=====", sym, "outside band -> signed NEXT one-minute return (n, bp, t), and signed PREVIOUS one-minute return")
    for lab, cond in (("all minutes 10:00-15:58", np.ones(391, bool)), ("minute :00", moh == 0), ("minute :30", moh == 30), (":00 or :30", (moh == 0) | (moh == 30)),
                      (":15 or :45", (moh == 15) | (moh == 45)), (":05,:10,:20,:25,:35,:40,:50,:55", np.isin(moh, [5, 10, 20, 25, 35, 40, 50, 55])),
                      ("other minutes (not multiple of 5)", moh % 5 != 0), (":01 or :31", (moh == 1) | (moh == 31)), (":59 or :29", (moh == 59) | (moh == 29))):
        w = sel(cond)
        print(f"   {lab:<36} next:", ts((sd * nxt1)[w]), " prev:", ts((sd * prv1)[w]))
    # first minute of being outside (fresh breach: inside at m-1, outside at m) vs continuing outside
    fresh = np.zeros_like(sd, bool); fresh[:, 1:] = (sd[:, 1:] != 0) & (sd[:, :-1] == 0)
    w = fresh & (mins[None, :] >= 30) & (mins[None, :] <= 388)
    print("   fresh breach (inside the minute before): next:", ts((sd * nxt1)[w]), " prev:", ts((sd * prv1)[w]))
    w = fresh & ((moh == 0) | (moh == 30))[None, :] & (mins[None, :] >= 30) & (mins[None, :] <= 388)
    print("   fresh breach at :00/:30                  next:", ts((sd * nxt1)[w]), " prev:", ts((sd * prv1)[w]))
    r2.free()
