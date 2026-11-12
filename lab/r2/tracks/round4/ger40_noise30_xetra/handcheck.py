"""Independent recomputation of 25 trades of configuration 1 from raw M1 bars, by timestamp lookups (no grid code).
IN SAMPLE ONLY.  For each trade: O (09:00 bar open), PC (previous session's 17:29 close), P(T) (close of the T-1 bar),
sigma(T) (mean of |P(T)/O - 1| over the previous 14 sessions, at least 9), UB / LB, the entry condition, the stop, the
fill price (ask/bid open +/- 0.2 bp), and the exit (check exit: the first later check back inside the band; stop: the
first bar whose bid low / ask high reaches the stop; else 17:25).  Output: handcheck.json

    PYTHONDONTWRITEBYTECODE=1 python3 handcheck.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xetra as X  # noqa: E402


def main(k=25, seed=11):
    m1 = X.load_is()
    t = pd.read_parquet(os.path.join(X.RES, "trades_01_main.parquet"))
    mid_o = (m1.bo + m1.ao) / 2
    mid_c = (m1.bc + m1.ac) / 2
    ber = m1.index.tz_convert(X.BER)
    sess, early, skip = X.sessions_between(dt_first(ber), dt_last(ber))
    sess = list(sess)

    def at(day, hh, mm):
        return pd.Timestamp(f"{day} {hh:02d}:{mm:02d}").tz_localize(X.BER).tz_convert("UTC")

    def price_at(day, minute):                      # close of the last bar starting before T, if at most 11 min old
        T = at(day, minute // 60, minute % 60)
        j = m1.index.searchsorted(T, side="left") - 1
        if j < 0 or (T - m1.index[j]) > pd.Timedelta(minutes=11):
            return np.nan
        return float(mid_c.iloc[j])

    def open_0900(day):
        T = at(day, 9, 0)
        return float(mid_o.loc[T]) if T in m1.index else np.nan

    rng = np.random.default_rng(seed)
    pick = np.sort(rng.choice(len(t), k, replace=False))
    out, bad = [], 0
    for j in pick:
        tr = t.iloc[j]
        day = pd.Timestamp(str(tr["sdate"])).date()
        di = sess.index(day)
        O = open_0900(day)
        PC = price_at(sess[di - 1], 1050)
        m_in = int(tr["m_in"])
        P = price_at(day, m_in)
        vals = []
        for dd in sess[max(0, di - 14):di]:
            o_ = open_0900(dd)
            p_ = price_at(dd, m_in)
            if np.isfinite(o_) and np.isfinite(p_):
                vals.append(abs(p_ / o_ - 1))
        sig = float(np.mean(vals)) if len(vals) >= 9 else np.nan
        UB, LB = max(O, PC) * (1 + sig), min(O, PC) * (1 - sig)
        side = 1 if P > UB else (-1 if P < LB else 0)
        stop = max(O, PC) if side > 0 else min(O, PC)
        T_in = at(day, m_in // 60, m_in % 60)
        ei = m1.index.searchsorted(T_in, side="left")
        reversal = bool(tr["entry_time"] == m1.index[ei + 1])
        if reversal:
            ei += 1                                   # reversal at the same check: entry one bar later (noise30)
        fill = float(m1.ao.iloc[ei]) * (1 + 0.2e-4) if side > 0 else float(m1.bo.iloc[ei]) * (1 - 0.2e-4)
        # exit: walk forward bar by bar from the fill; checks every 30 min from the next check on; 17:25 time exit
        x_time = at(day, 17, 25)
        xi_time = m1.index.searchsorted(x_time, side="left")
        later = [mm for mm in range(570, 1021, 30) if mm > m_in]
        chk = {}
        for mm in later:
            Tm = at(day, mm // 60, mm % 60)
            e2 = m1.index.searchsorted(Tm, side="left")
            if e2 >= xi_time or (m1.index[e2] - Tm) > pd.Timedelta(minutes=5):
                continue
            p2 = price_at(day, mm)
            v2 = []
            for dd in sess[max(0, di - 14):di]:
                o_, p_ = open_0900(dd), price_at(dd, mm)
                if np.isfinite(o_) and np.isfinite(p_):
                    v2.append(abs(p_ / o_ - 1))
            if len(v2) < 9 or not np.isfinite(p2):
                continue
            s2 = float(np.mean(v2))
            ub2, lb2 = max(O, PC) * (1 + s2), min(O, PC) * (1 - s2)
            if (side > 0 and p2 < ub2) or (side < 0 and p2 > lb2):
                chk = {"bar": e2, "minute": mm}
                break
        x_bar = chk.get("bar", xi_time)
        bl, ah = m1.bl.to_numpy(), m1.ah.to_numpy()
        seg = np.arange(ei, x_bar)
        hit = seg[(bl[seg] <= stop)] if side > 0 else seg[(ah[seg] >= stop)]
        if len(hit):
            reason, x_t = "stop", m1.index[hit[0]] + pd.Timedelta(minutes=1)
        else:
            reason, x_t = "time", m1.index[x_bar]
        rec = {"session": str(day), "check_berlin": f"{m_in // 60:02d}:{m_in % 60:02d}", "side": side,
               "side_engine": int(tr["side"]), "O": O, "O_engine": float(tr["o_px"]), "PC": PC,
               "PC_engine": float(tr["pc_px"]), "sigma": sig, "sigma_engine": float(tr["sig"]), "P": P,
               "P_engine": float(tr["psig"]), "stop": stop, "stop_engine": float(tr["stop"]), "fill": fill,
               "fill_engine": float(tr["entry"]), "exit_reason": reason, "exit_reason_engine": str(tr["reason"]),
               "exit_time": str(x_t), "exit_time_engine": str(tr["exit_time"])}
        ok = (side == rec["side_engine"] and np.isclose(O, rec["O_engine"], rtol=0, atol=1e-9)
              and np.isclose(PC, rec["PC_engine"], rtol=0, atol=1e-9) and np.isclose(sig, rec["sigma_engine"], rtol=1e-12)
              and np.isclose(P, rec["P_engine"], rtol=0, atol=1e-9) and np.isclose(stop, rec["stop_engine"], rtol=0, atol=1e-9)
              and np.isclose(fill, rec["fill_engine"], rtol=1e-12) and reason == rec["exit_reason_engine"]
              and str(x_t) == rec["exit_time_engine"])
        rec["match"] = bool(ok)
        bad += not ok
        out.append(rec)
    res = {"trades_checked": len(out), "matches": len(out) - bad, "seed": seed, "cases": out}
    with open(os.path.join(X.RES, "handcheck.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print({"trades_checked": len(out), "matches": len(out) - bad})
    for r in out:
        if not r["match"]:
            print(json.dumps(r, default=str))


def dt_first(ber):
    return ber[0].date()


def dt_last(ber):
    return ber[-1].date()


if __name__ == "__main__":
    main()
