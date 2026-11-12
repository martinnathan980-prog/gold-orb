"""Hand check (declared.json R23 b): 6 days of the main recomputed from the raw in-sample bars with plain loops and
timestamp lookups (no grid, no rolling, no vectorised simulator): the previous trading day from the NYSE calendar,
d of both indices, sd_d, h, sd_pi (with each previous day's own h), the condition, then the pair's path minute by
minute, the stop and the exit. Compared with signals_main.parquet / trades_01_main.parquet.
Writes results/r2/round4/letf_close_pair/handcheck.json."""
import datetime as dtm
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402  (only the loader, idxus_lib and constants are used)

NY = C.NY
SM, SS = C.SLIP_M, C.SLIP_S


def ts(day, hhmm):
    return pd.Timestamp(f"{day} {hhmm}").tz_localize(NY).tz_convert("UTC")


class Raw:
    def __init__(self, fr):
        self.fr = fr
        self.ix = {s: set(f.index) for s, f in fr.items()}

    def bar(self, sym, t):
        return self.fr[sym].loc[t] if t in self.ix[sym] else None

    def mid_c(self, sym, t):
        b = self.bar(sym, t)
        return np.nan if b is None else (b.bc + b.ac) / 2

    def mid_o(self, sym, t):
        b = self.bar(sym, t)
        return np.nan if b is None else (b.bo + b.ao) / 2

    def first_at_or_after(self, sym, t, col, until):
        f = self.fr[sym]
        k = f.index.searchsorted(t)
        if k < len(f) and f.index[k] <= until:
            return float(f[col].iloc[k])
        return None


def nyse_day_kind(d):
    full, half = C.idxus_lib.us_holidays(d.year)
    if d.weekday() >= 5 or d in full:
        return "closed"
    return "half" if d in half else "full"


def prev_trading_day(d):
    p = d - dtm.timedelta(days=1)
    while nyse_day_kind(p) == "closed":
        p -= dtm.timedelta(days=1)
    return p


def main():
    fr = C.load_frames(syms=("us100", "us30"))
    raw = Raw(fr)
    sig = pd.read_parquet(os.path.join(C.OUT, "signals_main.parquet"))
    tr = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    sessions = [d.date() for d in sig.date]
    pos = {d: i for i, d in enumerate(sessions)}
    picks = list(tr[tr.reason == "stop"].sample(2, random_state=1).session) + \
        list(tr[tr.reason == "time"].sample(2, random_state=2).session)
    rng = np.random.default_rng(21)
    nontrade = sig.index[(~sig["take"]) & sig["sd_d"].notna() & sig["sd_pi"].notna() & sig["d_us100"].notna()]
    picks += list(rng.choice(nontrade, 2, replace=False))
    cache_d, cache_r, cache_h = {}, {}, {}

    def d_of(j):
        if j not in cache_d:
            day = sessions[j]
            p = prev_trading_day(day)
            if nyse_day_kind(p) == "half":
                cache_d[j] = (np.nan, np.nan)
            else:
                cache_d[j] = tuple(np.log(raw.mid_c(s, ts(day, "15:29")) / raw.mid_c(s, ts(p, "15:59")))
                                   for s in ("us100", "us30"))
        return cache_d[j]

    def ret_of(j):
        if j not in cache_r:
            day = sessions[j]
            cache_r[j] = tuple(np.log(raw.mid_o(s, ts(day, "15:59")) / raw.mid_o(s, ts(day, "15:30")))
                               for s in ("us100", "us30"))
        return cache_r[j]

    def sd_fin(v, minv=40):
        v = np.array([x for x in v if np.isfinite(x)])
        return float(np.std(v, ddof=1)) if len(v) >= minv else np.nan

    def h_of(j):
        if j not in cache_h:
            prev = range(max(j - 60, 0), j)
            cache_h[j] = sd_fin([ret_of(i)[0] for i in prev]) / sd_fin([ret_of(i)[1] for i in prev])
        return cache_h[j]

    out, bad = [], []
    for j in picks:
        j = int(j)
        day = sessions[j]
        d100, d30 = d_of(j)
        prev = range(max(j - 60, 0), j)
        sd_d = sd_fin([d_of(i)[0] for i in prev])
        h = h_of(j)
        pis = []
        for i in prev:
            di = d_of(i)[0]
            if not np.isfinite(di) or di == 0:
                continue
            hi = h_of(i)
            ri = ret_of(i)
            pis.append(np.sign(di) * (ri[0] - hi * ri[1]))
        sdpi = sd_fin(pis)
        cond = bool(np.isfinite(d100) and np.isfinite(d30) and d100 != 0 and np.sign(d100) == np.sign(d30)
                    and np.isfinite(sd_d) and abs(d100) >= 1.25 * sd_d)
        take = bool(cond and np.isfinite(h) and h > 0 and np.isfinite(sdpi) and sdpi > 0)
        row = {"date": str(day), "prev_trading_day": str(prev_trading_day(day)), "d_us100": d100, "d_us30": d30,
               "sd_d": sd_d, "h": h, "sd_pi": sdpi, "cond": cond, "take": take}
        s = sig.iloc[j]
        if bool(s["take"]) != take or bool(s["cond"]) != cond:
            bad.append(f"{day} take/cond: {take}/{cond} vs {s['take']}/{s['cond']}")
        for kk, col in (("d_us100", "d_us100"), ("d_us30", "d_us30"), ("sd_d", "sd_d"), ("h", "h"), ("sd_pi", "sd_pi")):
            a, b = row[kk], s[col]
            if not ((np.isnan(a) and np.isnan(b)) or np.isclose(a, b, rtol=1e-9, atol=0)):
                bad.append(f"{day} {kk}: {a} vs {b}")
        if take:
            dr = int(np.sign(d100))
            legs = (("us100", dr, 1.0), ("us30", -dr, h))
            t0 = ts(day, "15:30")
            fills = {}
            for sym, sd, w in legs:
                b = raw.bar(sym, t0)
                fills[sym] = b.ao * (1 + SM) if sd > 0 else b.bo * (1 - SM)
            last = {"us100": None, "us30": None}
            stop_at = None
            for m in range(29):                                     # closes of the 15:30 .. 15:58 bars
                t = t0 + pd.Timedelta(minutes=m)
                pi = 0.0
                for sym, sd, w in legs:
                    b = raw.bar(sym, t)
                    if b is not None:
                        last[sym] = b.bc if sd > 0 else b.ac
                    pi += w * sd * np.log(last[sym] / fills[sym])
                if pi <= -1.5 * sdpi:
                    stop_at = m
                    break
            tx = t0 + pd.Timedelta(minutes=stop_at + 1) if stop_at is not None else ts(day, "15:59")
            sl = SS if stop_at is not None else SM
            until = ts(day, "16:59")
            net = 0.0
            for sym, sd, w in legs:
                q = raw.first_at_or_after(sym, tx, "bo" if sd > 0 else "ao", until)
                ex = q * (1 - sl) if sd > 0 else q * (1 + sl)
                net += w * sd * np.log(ex / fills[sym])
            R = net / (1.5 * sdpi)
            row.update({"dir": dr, "stop_decision_minute_after_15:30": stop_at, "exit_utc": str(tx),
                        "net_pi_bp": net * 1e4, "R": R})
            tt = tr[tr.session == j].iloc[0]
            if not np.isclose(R, tt.R, rtol=1e-9):
                bad.append(f"{day} R: {R} vs {tt.R}")
            if (stop_at is None) != (tt.reason == "time") or (stop_at is not None and stop_at != tt.stop_decision_col):
                bad.append(f"{day} exit decision differs")
            if int(tt.dir) != dr:
                bad.append(f"{day} direction differs")
            row["pipeline_R"] = float(tt.R)
        out.append(row)
    res = {"days_checked": len(out), "rows": out, "problems": bad, "pass": not bad}
    C.jdump(res, os.path.join(C.OUT, "handcheck.json"))
    for rw in out:
        print(rw)
    print("problems:", bad)


if __name__ == "__main__":
    main()
