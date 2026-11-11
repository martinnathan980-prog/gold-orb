"""Independent quick replica of noise30 / ocm4 (lab r2/tracks/idx_us/strategy.py docstring), IN-SAMPLE ONLY (< 2022).
Mid-price signals, fills at the open of the minute bar at T (mid), costs applied afterwards.
Not the lab engine: no bid/ask stop logic, no slippage. Purpose: order-of-magnitude check of gross edge."""
import sys, glob, datetime as dt
import numpy as np, pandas as pd
from zoneinfo import ZoneInfo

DK = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/dk/"
END = pd.Timestamp("2022-01-01", tz="UTC")


def load_duka(sym):
    out = {}
    for side in ("bid", "ask"):
        fs = sorted(glob.glob(f"{DK}{sym}-{side}-*.csv"))
        d = pd.concat([pd.read_csv(f) for f in fs if open(f).read(1)], ignore_index=True)
        d.index = pd.to_datetime(d.pop("timestamp"), unit="ms", utc=True)
        out[side] = d[~d.index.duplicated()]
    b, a = out["bid"], out["ask"]
    ix = b.index.intersection(a.index)
    b, a = b.loc[ix], a.loc[ix]
    m = pd.DataFrame({"o": (b.open + a.open) / 2, "h": (b.high + a.high) / 2, "l": (b.low + a.low) / 2,
                      "c": (b.close + a.close) / 2, "spr": (a.close - b.close)}, index=ix)
    flat = (b.open == b.close) & (b.high == b.low) & (b.volume == 0)
    m = m[~flat]
    return m[m.index < END]


def load_lab(sym):
    d = pd.read_parquet(f"/home/user/gold-orb/lab/data/{sym}_m1.parquet")
    d = d[d.index < END]          # in-sample only, validation years never touched
    return pd.DataFrame({"o": (d.bo + d.ao) / 2, "h": (d.bh + d.ah) / 2, "l": (d.bl + d.al) / 2,
                         "c": (d.bc + d.ac) / 2, "spr": d.ac - d.bc}, index=d.index)


def jp_holidays():
    H = set()
    def nth(y, mo, n):  # n-th Monday
        d = dt.date(y, mo, 1)
        d += dt.timedelta(days=(0 - d.weekday()) % 7)
        return d + dt.timedelta(days=7 * (n - 1))
    ve = {2014: 21, 2015: 21, 2016: 20, 2017: 20, 2018: 21, 2019: 21, 2020: 20, 2021: 20}
    ae = {2014: 23, 2015: 23, 2016: 22, 2017: 23, 2018: 23, 2019: 23, 2020: 22, 2021: 23}
    for y in range(2014, 2022):
        hs = [dt.date(y, 1, 1), dt.date(y, 1, 2), dt.date(y, 1, 3), dt.date(y, 12, 31), nth(y, 1, 2), dt.date(y, 2, 11),
              dt.date(y, 3, ve[y]), dt.date(y, 4, 29), dt.date(y, 5, 3), dt.date(y, 5, 4), dt.date(y, 5, 5),
              nth(y, 9, 3), dt.date(y, 9, ae[y]), dt.date(y, 11, 3), dt.date(y, 11, 23)]
        hs.append(dt.date(y, 12, 23) if y <= 2018 else None)
        if y >= 2020: hs.append(dt.date(y, 2, 23))
        if y == 2020: hs += [dt.date(2020, 7, 23), dt.date(2020, 7, 24), dt.date(2020, 8, 10)]
        elif y == 2021: hs += [dt.date(2021, 7, 22), dt.date(2021, 7, 23), dt.date(2021, 8, 9)]
        else:
            hs += [nth(y, 7, 3), nth(y, 10, 2)]
            if y >= 2016: hs.append(dt.date(y, 8, 11))
        if y == 2019: hs += [dt.date(2019, 4, 30), dt.date(2019, 5, 1), dt.date(2019, 5, 2), dt.date(2019, 10, 22)]
        if y == 2015: hs.append(dt.date(2015, 9, 22))
        hs = [h for h in hs if h]
        S = set(hs)
        for h in hs:                      # substitute holiday
            if h.weekday() == 6:
                s = h + dt.timedelta(days=1)
                while s in S: s += dt.timedelta(days=1)
                S.add(s)
        H |= S
    return H


def us_skip():
    sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/idx_us")
    import idxus_lib as cm
    S = set()
    for y in range(2013, 2022):
        f, h = cm.us_holidays(y)
        S |= f | h
    return S


def grid(m, tz, open_min, L, skip, first_date):
    loc = m.index.tz_convert(ZoneInfo(tz))
    mins = loc.hour * 60 + loc.minute - open_min
    ok = (mins >= 0) & (mins < L) & (loc.weekday < 5)
    dates = np.array(loc.date)[ok]
    k = np.asarray(mins[ok])
    ud = np.array(sorted(set(dates)))
    ud = np.array([d for d in ud if d not in skip and d >= first_date])
    di = {d: i for i, d in enumerate(ud)}
    row = np.array([di.get(d, -1) for d in dates])
    sel = row >= 0
    D = len(ud)
    A = {c: np.full((D, L), np.nan) for c in "ohlc"}
    A["spr"] = np.full((D, L), np.nan)
    sub = m[ok][sel]
    for c in A:
        A[c][row[sel], k[sel]] = sub[c].to_numpy()
    # P[d, T] = close of the last bar that started before T, at most 10 minutes old (T = 0..L)
    cf = pd.DataFrame(A["c"]).ffill(axis=1, limit=9).to_numpy()
    P = np.full((D, L + 1), np.nan)
    P[:, 1:] = cf
    O = A["o"][:, 0]
    # sessions need an open bar and at least 60% of bars
    good = np.isfinite(O) & (np.isfinite(A["c"]).mean(axis=1) > 0.6)
    return ud, A, P, O, good


def daily_atr(m, n=14):
    ny = m.index.tz_convert(ZoneInfo("America/New_York")) + pd.Timedelta(hours=7)
    day = pd.Series(ny.date, index=m.index)
    g = m.groupby(day.to_numpy())
    db = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.c.size(), "end": g.apply(lambda x: x.index[-1])})
    db = db[db.n >= 600]
    pc = db.c.shift(1)
    tr = np.maximum(db.h - db.l, np.maximum((db.h - pc).abs(), (db.l - pc).abs()))
    db["atr"] = tr.rolling(n).mean()
    return db


def fill_px(A, P, d, T):
    v = A["o"][d, T] if T < A["o"].shape[1] else np.nan
    if np.isfinite(v): return v
    if np.isfinite(P[d, T]): return P[d, T]
    c = A["c"][d, :T]; c = c[np.isfinite(c)]
    return c[-1] if len(c) else np.nan


def noise(ud, A, P, O, good, checks, exit_T, pc_T, lookback=14):
    D = len(ud)
    PC = np.full(D, np.nan)
    PC[1:] = P[:-1, pc_T]
    PC[1:][~good[:-1]] = np.nan
    absmv = np.abs(P / O[:, None] - 1)
    absmv[~good] = np.nan
    tr = []
    for d in range(lookback, D):
        if not good[d]: continue
        w = absmv[d - lookback:d]
        o = O[d]; pc = PC[d]
        hi_ref = max(o, pc) if np.isfinite(pc) else o
        lo_ref = min(o, pc) if np.isfinite(pc) else o
        state = 0; pos = None; stopped = False
        def close(T, px, reason):
            nonlocal pos
            e = pos
            ret = e["s"] * (px / e["px"] - 1)
            sp = (e["spr"] + (A["spr"][d, min(T, A["spr"].shape[1] - 1)] if np.isfinite(A["spr"][d, min(T, A["spr"].shape[1] - 1)]) else e["spr"])) / 2
            tr.append((ud[d], e["T"], T, e["s"], ret * 1e4, sp / e["px"] * 1e4, ret / e["risk"], e["risk"] * 1e4, reason))
            pos = None
        for i, T in enumerate(checks):
            p = P[d, T]
            col = w[:, T]
            if not np.isfinite(p) or np.isfinite(col).sum() < 9:
                continue
            sig = np.nanmean(col)
            UB = hi_ref * (1 + sig); LB = lo_ref * (1 - sig)
            # stop check since last check is done below (after entry) -- here handle (a)
            if state == 1 and p < UB:
                if pos: close(T, fill_px(A, P, d, T), "band")
                state = 0
            elif state == -1 and p > LB:
                if pos: close(T, fill_px(A, P, d, T), "band")
                state = 0
            if state == 0:
                s = 1 if p > UB else (-1 if p < LB else 0)
                if s:
                    px = fill_px(A, P, d, T)
                    stop = hi_ref if s == 1 else lo_ref
                    risk = abs(px / stop - 1)
                    if risk <= 0: continue
                    spr = A["spr"][d, T] if np.isfinite(A["spr"][d, T]) else np.nanmedian(A["spr"][d])
                    pos = {"s": s, "px": px, "T": T, "stop": stop, "risk": risk, "spr": spr}
                    state = s
            if pos:   # hard stop until the next check / exit
                nxt = checks[i + 1] if i + 1 < len(checks) else exit_T
                nxt = min(nxt, exit_T)
                seg_l = A["l"][d, T:nxt]; seg_h = A["h"][d, T:nxt]
                hit = np.flatnonzero(seg_l <= pos["stop"]) if pos["s"] == 1 else np.flatnonzero(seg_h >= pos["stop"])
                if len(hit):
                    close(T + int(hit[0]), pos["stop"], "stop")
        if pos:
            close(exit_T, fill_px(A, P, d, exit_T), "time")
    return pd.DataFrame(tr, columns=["date", "Tin", "Tout", "side", "gross_bp", "spr_bp", "R", "risk_bp", "reason"])


def ocm(ud, A, P, O, good, db, tz, open_min, n=4, exit_T=385, size_win=20, k=0.3):
    D = len(ud)
    move = P[:, n] / O - 1
    cnt = np.isfinite(A["c"][:, :n]).sum(axis=1)
    move[(cnt < n - 1) | ~good] = np.nan
    am = pd.Series(np.abs(move))
    med = am.shift(1).rolling(size_win, min_periods=10).median().to_numpy()
    z = ZoneInfo(tz)
    ends = db.end.to_numpy(); atrv = db.atr.to_numpy()
    ends_ns = pd.DatetimeIndex(db.end).asi8
    tr = []
    for d in range(D):
        if not np.isfinite(move[d]) or not np.isfinite(med[d]) or abs(move[d]) < med[d] or move[d] == 0: continue
        t = pd.Timestamp(dt.datetime.combine(ud[d], dt.time(open_min // 60, open_min % 60)), tz=z) + pd.Timedelta(minutes=n)
        j = np.searchsorted(ends_ns, t.tz_convert("UTC").value // (10 ** 9 // (10 ** 9 // 1)) if False else pd.Timestamp(t.tz_convert("UTC")).asm8.astype(ends_ns.dtype if hasattr(ends_ns, "dtype") else "int64").astype("int64") if False else 0)
        tr.append((d, t))
    # ATR lookup vectorised
    if not tr: return pd.DataFrame()
    tt = pd.DatetimeIndex([x[1].tz_convert("UTC") for x in tr])
    endix = pd.DatetimeIndex(db.end)
    if endix.tz is None: endix = endix.tz_localize("UTC")
    j = np.searchsorted(endix.as_unit("ns").asi8, tt.as_unit("ns").asi8, side="left") - 1
    # last COMPLETED day: its last bar must be older than the decision by construction (end < t); require the day closed (>= 30 min gap not checked)
    out = []
    for (d, t), jj in zip(tr, j):
        if jj < 0 or not np.isfinite(atrv[jj]): continue
        # if the daily bar containing "now" is jj (still running), use jj-1
        px = fill_px(A, P, d, n)
        s = 1 if move[d] > 0 else -1
        a = atrv[jj]
        stop = px - s * k * a
        risk = k * a / px
        seg_l = A["l"][d, n:exit_T]; seg_h = A["h"][d, n:exit_T]
        hit = np.flatnonzero(seg_l <= stop) if s == 1 else np.flatnonzero(seg_h >= stop)
        if len(hit):
            xp, T, reason = stop, n + int(hit[0]), "stop"
        else:
            xp, T, reason = fill_px(A, P, d, exit_T), exit_T, "time"
        ret = s * (xp / px - 1)
        s1 = A["spr"][d, n]; s2 = A["spr"][d, min(T, A["spr"].shape[1] - 1)]
        s1 = s1 if np.isfinite(s1) else np.nanmedian(A["spr"][d]); s2 = s2 if np.isfinite(s2) else s1
        out.append((ud[d], n, T, s, ret * 1e4, (s1 + s2) / 2 / px * 1e4, ret / risk, risk * 1e4, reason))
    return pd.DataFrame(out, columns=["date", "Tin", "Tout", "side", "gross_bp", "spr_bp", "R", "risk_bp", "reason"])


def stats(tr, label, costs=()):
    if not len(tr):
        print(label, "no trades"); return
    tr = tr[np.isfinite(tr.gross_bp)]
    g = tr.gross_bp.to_numpy()
    def line(x, name):
        t = x.mean() / x.std(ddof=1) * np.sqrt(len(x))
        pf = x[x > 0].sum() / -x[x < 0].sum()
        return f"{name}: mean {x.mean():+.2f} bp  t {t:+.2f}  PF {pf:.3f}"
    yrs = pd.Series(g, index=pd.to_datetime(tr.date)).groupby(lambda x: x.year)
    print(f"== {label}: n {len(tr)} ({len(tr) / max(1, len(set(pd.to_datetime(tr.date).dt.year))):.0f}/yr)  sd {g.std():.1f} bp  win {np.mean(g > 0) * 100:.0f}%  median risk {tr.risk_bp.median():.0f} bp  stop exits {np.mean(tr.reason == 'stop') * 100:.0f}%")
    print("   " + line(g, "gross"))
    print("   " + line(g - tr.spr_bp.to_numpy(), f"net of Dukascopy spread (median {tr.spr_bp.median():.2f} bp, mean {tr.spr_bp.mean():.2f})"))
    for c in costs:
        print("   " + line(g - c, f"net of flat {c} bp"))
    print("   long: " + line(g[tr.side == 1], "gross") + " | short: " + line(g[tr.side == -1], "gross"))
    print("   gross bp/trade by year: " + "  ".join(f"{y}:{v.mean():+.1f}({len(v)})" for y, v in yrs))


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "jp":
        m = load_duka("jpnidxjpy")
        print("rows", len(m), m.index[0], m.index[-1])
        db = daily_atr(m)
        for lab, skip in (("JP holidays skipped", jp_holidays()), ("no holiday filter", set())):
            ud, A, P, O, good = grid(m, "Asia/Tokyo", 540, 360, skip, dt.date(2014, 1, 1))
            sp = A["spr"] / A["c"] * 1e4
            print(lab, "sessions", len(ud), "good", good.sum(), "| session spread bp median", round(float(np.nanmedian(sp)), 2),
                  "points median", round(float(np.nanmedian(A["spr"])), 1), "| 09:00-09:10 median bp", round(float(np.nanmedian(sp[:, :10])), 2))
            sess = P[:, 355] / O - 1
            print("   open->14:55 move: sd %.0f bp, mean abs %.0f bp" % (np.nanstd(sess) * 1e4, np.nanmean(np.abs(sess)) * 1e4))
            cA = [30, 60, 90, 120, 210, 240, 270, 300, 330]
            cB = list(range(30, 331, 30))
            cC = [30, 60, 90, 120, 150, 210, 240, 270, 300, 330]
            for nm, ch in (("noise30 no-lunch-checks (09:30-11:00,12:30-14:30)", cA), ("noise30 incl 11:30", cC), ("noise30 every 30 min through lunch", cB)):
                tr = noise(ud, A, P, O, good, ch, 355, 359)
                stats(tr, f"JP225 {nm} [{lab}]", (1.6, 2.5, 3.6))
                if nm.startswith("noise30 no-lunch") and lab.startswith("JP"):
                    tr.to_csv(DK + "../jp_noise.csv", index=False)
            tr = ocm(ud, A, P, O, good, db, "Asia/Tokyo", 540, n=4, exit_T=355)
            stats(tr, f"JP225 ocm4 [{lab}]", (1.6, 2.5, 3.6))
            if lab.startswith("JP"): tr.to_csv(DK + "../jp_ocm.csv", index=False)
            for n in (3, 5):
                stats(ocm(ud, A, P, O, good, db, "Asia/Tokyo", 540, n=n, exit_T=355), f"JP225 ocm{n} neighbour [{lab}]", ())
    else:
        skip = us_skip()
        res = {}
        for sym, src, first in (("us100", "lab", dt.date(2014, 1, 1)), ("us2000", "duka", dt.date(2019, 3, 21))):
            m = load_lab("us100") if src == "lab" else load_duka("ussc2000idxusd")
            print(sym, "rows", len(m), m.index[0], m.index[-1])
            db = daily_atr(m)
            ud, A, P, O, good = grid(m, "America/New_York", 570, 390, skip, first)
            sp = A["spr"] / A["c"] * 1e4
            print("  sessions", len(ud), "good", good.sum(), "| session spread bp median", round(float(np.nanmedian(sp)), 2), "points", round(float(np.nanmedian(A["spr"])), 2))
            sess = P[:, 385] / O - 1
            print("   open->15:55 move: sd %.0f bp" % (np.nanstd(sess) * 1e4))
            ch = list(range(30, 361, 30))
            tn = noise(ud, A, P, O, good, ch, 385, 389)
            to = ocm(ud, A, P, O, good, db, "America/New_York", 570, n=4, exit_T=385)
            stats(tn, f"{sym} noise30 (all IS available)", (0.8, 1.6, 2.4))
            stats(to, f"{sym} ocm4 (all IS available)", (0.8, 1.6, 2.4))
            res[sym] = (tn, to)
        # common window + spanning regression (daily gross bp of us2000 sleeves on us100 sleeves)
        import numpy.linalg as la
        start = dt.date(2019, 5, 20)
        def daily(tr, cost):
            x = tr[tr.date >= start]
            return (x.gross_bp - cost).groupby(x.date).sum()
        for cost2 in (0.0, 1.6, 2.4):
            y = daily(res["us2000"][0], cost2).add(daily(res["us2000"][1], cost2), fill_value=0)
            x1 = daily(res["us100"][0], 0.8); x2 = daily(res["us100"][1], 0.8)
            idx = sorted(set(y.index) | set(x1.index) | set(x2.index))
            Y = y.reindex(idx).fillna(0).to_numpy(); X = np.column_stack([np.ones(len(idx)), x1.reindex(idx).fillna(0), x2.reindex(idx).fillna(0)])
            b = la.lstsq(X, Y, rcond=None)[0]; e = Y - X @ b
            cov = la.inv(X.T @ X) * (e @ e) / (len(Y) - 3)
            print(f"spanning (us2000 both sleeves, cost {cost2} bp) days {len(Y)}: intercept {b[0]:+.2f} bp/day t {b[0] / np.sqrt(cov[0, 0]):+.2f}; beta noise {b[1]:.2f} ocm {b[2]:.2f}; corr(y, us100 sum) {np.corrcoef(Y, X[:, 1] + X[:, 2])[0, 1]:.2f}")
        for i, nm in ((0, "noise30"), (1, "ocm4")):
            a = res["us100"][i]; a = a[a.date >= start]
            stats(a, f"us100 {nm} on the us2000 window (2019-05..2021)", (0.8,))
