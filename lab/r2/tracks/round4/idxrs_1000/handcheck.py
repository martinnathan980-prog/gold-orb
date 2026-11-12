"""Hand check: a few days of the main recomputed from the raw in-sample bars with plain loops and timestamp lookups
(no grid, no rolling, no vectorised simulator): ranking, threshold, hedge, sd_pi, then the pair's path, stop and exit.
Compared with signals_main.parquet / trades_01_main.parquet. Writes results/r2/round4/idxrs_1000/handcheck.json."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402  (only the loader, the session calendar and constants are used)

NY = "America/New_York"


def ts(day, hhmm):
    return pd.Timestamp(f"{day.date()} {hhmm}").tz_localize(NY).tz_convert("UTC")


class Raw:
    def __init__(self, fr):
        self.fr = fr

    def bar(self, sym, t):
        f = self.fr[sym]
        return f.loc[t] if t in f.index else None

    def mid_o(self, sym, t):
        b = self.bar(sym, t)
        return np.nan if b is None else (b.bo + b.ao) / 2

    def mid_c(self, sym, t):
        b = self.bar(sym, t)
        return np.nan if b is None else (b.bc + b.ac) / 2


def day_stats(raw, day):
    r = [np.log(raw.mid_c(s, ts(day, "09:59")) / raw.mid_o(s, ts(day, "09:30"))) for s in C.SYMS]
    ret = [np.log(raw.mid_o(s, ts(day, "15:55")) / raw.mid_o(s, ts(day, "10:00"))) for s in C.SYMS]
    return np.array(r), np.array(ret)


def main():
    days = list(C.sessions())
    fr = C.load_frames()
    raw = Raw(fr)
    sig = pd.read_parquet(os.path.join(C.OUT, "signals_main.parquet"))
    tr = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    rng = np.random.default_rng(21)
    picks_trade = list(tr[tr.reason == "stop"].sample(2, random_state=1).session) + \
        list(tr[tr.reason == "time"].sample(2, random_state=2).session)
    nontrade = sig.index[(~sig["take"]) & sig["ranked"] & sig["Q"].notna() & sig["sd_pi"].notna()]
    picks = picks_trade + list(rng.choice(nontrade, 2, replace=False))
    cache = {}

    def stats(j):
        if j not in cache:
            cache[j] = day_stats(raw, days[j])
        return cache[j]

    def h_of(j):
        rets = np.array([stats(i)[1] for i in range(j - 60, j)])
        sd = []
        for k in range(3):
            v = rets[:, k][np.isfinite(rets[:, k])]
            sd.append(np.std(v, ddof=1) if len(v) >= 40 else np.nan)
        r = stats(j)[0]
        if not np.isfinite(r).all():
            return np.nan, None, None
        S, W = int(np.argmax(r)), int(np.argmin(r))
        return sd[S] / sd[W], S, W

    out, bad = [], []
    for j in picks:
        j = int(j)
        r, ret = stats(j)
        S, W = int(np.argmax(r)), int(np.argmin(r))
        D = r.max() - r.min()
        Dp = np.array([stats(i)[0].max() - stats(i)[0].min() for i in range(j - 60, j)])
        Dp = Dp[np.isfinite(Dp)]
        Q = np.quantile(Dp, 0.75)
        h, _, _ = h_of(j)
        pis = []
        for i in range(j - 60, j):
            hi, Si, Wi = h_of(i)
            if Si is None or not np.isfinite(hi):
                continue
            ri = stats(i)[1]
            v = ri[Si] - hi * ri[Wi]
            if np.isfinite(v):
                pis.append(v)
        sdpi = np.std(pis, ddof=1)
        take = D >= Q
        row = {"date": str(days[j].date()), "S": C.SYMS[S], "W": C.SYMS[W], "D": D, "Q": Q, "h": h, "sd_pi": sdpi,
               "take": bool(take)}
        s = sig.iloc[j]
        for kk, a, b in (("S", row["S"], s.S), ("W", row["W"], s.W), ("take", row["take"], bool(s["take"]))):
            if a != b:
                bad.append(f"{row['date']} {kk}: {a} vs {b}")
        for kk in ("D", "Q", "h", "sd_pi"):
            if not np.isclose(row[kk], s[kk], rtol=1e-9):
                bad.append(f"{row['date']} {kk}: {row[kk]} vs {s[kk]}")
        if take:
            # the pair's path, minute by minute, from the raw bars
            sS, sW = C.SYMS[S], C.SYMS[W]
            fS = raw.bar(sS, ts(days[j], "10:00")).ao * (1 + C.SLIP_M)
            fW = raw.bar(sW, ts(days[j], "10:00")).bo * (1 - C.SLIP_M)
            lastS, lastW = None, None
            stop_at = None
            t0 = ts(days[j], "10:00")
            for m in range(355):
                t = t0 + pd.Timedelta(minutes=m)
                bS, bW = raw.bar(sS, t), raw.bar(sW, t)
                lastS = bS.bc if bS is not None else lastS
                lastW = bW.ac if bW is not None else lastW
                pi = np.log(lastS / fS) - h * np.log(lastW / fW)
                if pi <= -1.5 * sdpi:
                    stop_at = m
                    break
            def first_open(sym, t, col):
                f = fr[sym]
                k = f.index.searchsorted(t)
                return float(f[col].iloc[k])
            if stop_at is not None:
                tx = t0 + pd.Timedelta(minutes=stop_at + 1)
                eS, eW = first_open(sS, tx, "bo") * (1 - C.SLIP_S), first_open(sW, tx, "ao") * (1 + C.SLIP_S)
            else:
                tx = ts(days[j], "15:55")
                eS, eW = first_open(sS, tx, "bo") * (1 - C.SLIP_M), first_open(sW, tx, "ao") * (1 + C.SLIP_M)
            net = np.log(eS / fS) - h * np.log(eW / fW)
            R = net / (1.5 * sdpi)
            row.update({"stop_decision_minute_after_10:00": stop_at, "exit_utc": str(tx), "net_pi_bp": net * 1e4, "R": R})
            tt = tr[tr.session == j].iloc[0]
            if not np.isclose(R, tt.R, rtol=1e-9):
                bad.append(f"{row['date']} R: {R} vs {tt.R}")
            if (stop_at is None) != (tt.reason == "time") or (stop_at is not None and stop_at != tt.stop_decision_col):
                bad.append(f"{row['date']} exit decision differs")
            row["pipeline_R"] = float(tt.R)
        out.append(row)
    res = {"days_checked": len(out), "rows": out, "problems": bad, "pass": not bad}
    C.jdump(res, os.path.join(C.OUT, "handcheck.json"))
    for rw in out:
        print(rw)
    print("problems:", bad)


if __name__ == "__main__":
    main()
