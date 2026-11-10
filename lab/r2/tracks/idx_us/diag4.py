"""IS-only data diagnostic: is there short-horizon return continuation in the M1 feed (lagged / smoothed quotes)?
1-minute mid-return autocorrelation in the cash session, by index and year; and the generic 'previous 5 minutes ->
next minute' continuation at ALL minutes (not only at rule times)."""
from harness import *     # noqa
import idxus_lib as cm
bpf = lambda a, b: (b / a - 1) * 1e4
res = {}
for sym in ("us100", "us500", "us30"):
    m1 = r2.load(sym, start="2014-01-01", end="2022-01-01")
    g = cm.grid(m1)
    P, half, dts = g["P"], g["half"], g["dates"]
    yrs = np.array([d.year for d in dts])
    R = bpf(P[:, :-1], P[:, 1:])            # (D, 390) one-minute returns, minute k = 09:30+k -> +1
    R = R[~half]; yy = yrs[~half]
    out = {}
    def ac(x, y):
        ok = np.isfinite(x) & np.isfinite(y)
        return round(float(np.corrcoef(x[ok], y[ok])[0, 1]), 4)
    out["ac1_all_minutes"] = ac(R[:, :-1].ravel(), R[:, 1:].ravel())
    out["ac2_all_minutes"] = ac(R[:, :-2].ravel(), R[:, 2:].ravel())
    out["ac1_by_year"] = {int(y): ac(R[yy == y][:, :-1].ravel(), R[yy == y][:, 1:].ravel()) for y in np.unique(yy)}
    # by time of day (first 15 min, 10:00-15:30, last 30)
    seg = {"09:30-09:45": (0, 15), "09:45-10:30": (15, 60), "10:30-15:30": (60, 360), "15:30-16:00": (360, 389)}
    out["ac1_by_segment"] = {k: ac(R[:, a:b - 1].ravel(), R[:, a + 1:b].ravel()) for k, (a, b) in seg.items()}
    # generic continuation: sign of the previous 5-minute return x next 1-minute return, all minutes k>=5
    r5 = bpf(P[~half][:, :-6], P[~half][:, 5:-1]); nx = R[:, 5:]
    x = (np.sign(r5) * nx).ravel(); x = x[np.isfinite(x)]
    out["prev5min_sign_x_next1min_bp(mean,t,n)"] = (round(float(x.mean()), 3), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 1), int(len(x)))
    # the same but only when the 5-minute move is large (> 2x its median abs)
    big = np.abs(r5) > 2 * np.nanmedian(np.abs(r5))
    xb = (np.sign(r5) * nx)[big]; xb = xb[np.isfinite(xb)]
    out["big_prev5min_sign_x_next1min_bp(mean,t,n)"] = (round(float(xb.mean()), 3), round(float(xb.mean() / (xb.std(ddof=1) / np.sqrt(len(xb)))), 1), int(len(xb)))
    # by minute-of-hour: is the continuation special at :00 / :30 / :35 ?
    mm = (np.arange(5, 390)[None, :] + 30) % 60
    s1 = np.sign(r5) * nx
    out["continuation_by_minute_of_hour_bp"] = {int(k): round(float(np.nanmean(s1[:, (mm[0] == k)])), 2) for k in (0, 1, 5, 10, 15, 20, 29, 30, 31, 35, 40, 45, 50, 55, 59)}
    # median abs 1-min return, and fraction of exactly-zero 1-min returns (staleness)
    out["median_abs_1min_bp"] = round(float(np.nanmedian(np.abs(R))), 2)
    out["share_zero_1min_returns"] = round(float(np.nanmean(R == 0)), 3)
    # variance ratio 5-min vs 1-min
    r5all = bpf(P[~half][:, 0:386:5], P[~half][:, 5:391:5])
    out["variance_ratio_5min_over_5x1min"] = round(float(np.nanvar(r5all) / (5 * np.nanvar(R))), 3)
    r30 = bpf(P[~half][:, 0:361:30], P[~half][:, 30:391:30])
    out["variance_ratio_30min_over_30x1min"] = round(float(np.nanvar(r30) / (30 * np.nanvar(R))), 3)
    res[sym] = out
    print("=====", sym)
    for k, v in out.items():
        print("  ", k, v)
    r2.free()
json.dump(res, open(os.path.join(RES, "diag_feed_autocorr.json"), "w"), indent=1, default=str)
