"""Hand check of the engine on individual trades of the main (in sample only): every number recomputed from the raw
in-sample M1 quotes with plain code that does not use common.py's calendar, ATR or the lab simulator:
- the week label from a plain count of NYSE days to the FOMC dates;
- the entry / exit bars and prices (ask / bid opens, 0.2 bp market slippage, 0.5 bp on stops);
- ATR(20): simple mean of the last 20 true ranges of NY-17:00 trading days with at least 600 M1 bars, before the entry day;
- stop hit or not from the bar lows / highs; swap nights (weekdays crossed, Friday x3); R.
Output: results/r2/round4/fomc_cycle/handcheck.json
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def nyse_list():
    out = []
    d = dt.date(2012, 12, 3)
    while d <= dt.date(2021, 12, 31):
        if d.weekday() < 5:
            full, _ = C.idxus_lib.us_holidays(d.year)
            if d not in full:
                out.append(d)
        d += dt.timedelta(days=1)
    return out


def plain_label(day, nyse, fomc):
    """Week label of `day` by direct counting (main: s = 0)."""
    k = nyse.index(day)
    pos = [nyse.index(f) for f in fomc]
    nxt = [p for p in pos if p - 1 > k]
    if nxt and -6 <= k - nxt[0] <= -2:
        return "W-1"
    cur = [p for p in pos if p - 1 <= k]
    if not cur:
        return None
    t = k - cur[-1]
    for w in range(7):
        if 5 * w - 1 <= t <= 5 * w + 3:
            return f"W{w}"
    return None


def main():
    us = C.load_is("us500")
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    nyse = nyse_list()
    fomc = [d.date() for d in C.FOMC]
    # plain daily bars
    ny = us.index.tz_convert(C.NY)
    td = (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize()
    mid_h = (us.bh + us.ah) / 2
    mid_l = (us.bl + us.al) / 2
    mid_c = (us.bc + us.ac) / 2
    g = pd.DataFrame({"h": mid_h.to_numpy(), "l": mid_l.to_numpy(), "c": mid_c.to_numpy(), "td": td}).groupby("td")
    daily = pd.DataFrame({"h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "n": g.h.size()})
    daily = daily[daily.n >= 600]
    pc = daily.c.shift(1)
    tr = pd.concat([daily.h - daily.l, (daily.h - pc).abs(), (daily.l - pc).abs()], axis=1).max(axis=1)
    picks = sorted(set([0, len(t) - 1] + list(np.flatnonzero(t.reason.to_numpy() == "stop")[:3])
                       + list(np.flatnonzero(t.entry_delay_min.to_numpy() > 5)[:2]) + list(np.flatnonzero(t.n_days.to_numpy() < 5)[:2])
                       + list(np.random.default_rng(7).choice(len(t), 6, replace=False))))
    rows, worst = [], 0.0
    for k in picks:
        r = t.iloc[k]
        side = int(r.side)
        last_day = pd.Timestamp(r.last_day).date()
        entry_day = pd.Timestamp(r.entry_day).date()
        lab_days = [nyse[nyse.index(entry_day) + 1 + j] for j in range(int(r.n_days))]
        labs = {plain_label(d, nyse, fomc) for d in lab_days}
        te = pd.Timestamp(dt.datetime.combine(entry_day, dt.time(15, 55))).tz_localize(C.NY).tz_convert("UTC")
        tx = pd.Timestamp(dt.datetime.combine(last_day, dt.time(15, 55))).tz_localize(C.NY).tz_convert("UTC")
        ei = int(np.searchsorted(us.index.values, te.to_datetime64()))
        xi = int(np.searchsorted(us.index.values, tx.to_datetime64()))
        if xi >= len(us) or (us.index[xi] - tx) > pd.Timedelta(minutes=30):
            xi -= 1
        e_px = us.ao.iloc[ei] * (1 + 0.2e-4) if side > 0 else us.bo.iloc[ei] * (1 - 0.2e-4)
        prev = tr[tr.index < pd.Timestamp(entry_day)]
        atr = float(prev.iloc[-20:].mean()) if len(prev) >= 20 else np.nan
        stop = e_px - side * 3 * atr
        seg = us.iloc[ei:xi]
        if side > 0:
            hit = np.flatnonzero(seg.bl.to_numpy() <= stop)
        else:
            hit = np.flatnonzero(seg.ah.to_numpy() >= stop)
        if len(hit):
            j = ei + hit[0]
            if side > 0:
                px = stop if j == ei else min(stop, us.bo.iloc[j])
                x_px, x_t = px * (1 - 0.5e-4), us.index[j] + pd.Timedelta(minutes=1)
            else:
                px = stop if j == ei else max(stop, us.ao.iloc[j])
                x_px, x_t = px * (1 + 0.5e-4), us.index[j] + pd.Timedelta(minutes=1)
            reason = "stop"
        else:
            x_px = us.bo.iloc[xi] * (1 - 0.2e-4) if side > 0 else us.ao.iloc[xi] * (1 + 0.2e-4)
            x_t, reason = us.index[xi], "time"
        d0 = (us.index[ei].tz_convert(C.NY) + pd.Timedelta(hours=7)).date()
        d1 = ((x_t - pd.Timedelta(seconds=1)).tz_convert(C.NY) + pd.Timedelta(hours=7)).date()
        nights = 0
        d = d0
        while d < d1:
            if d.weekday() < 5:
                nights += 3 if d.weekday() == 4 else 1
            d += dt.timedelta(days=1)
        swap = e_px * 0.055 / 360 * nights if side > 0 else 0.0
        R = (side * (x_px - e_px) - swap) / abs(e_px - stop)
        chk = {"k": int(k), "label_engine": r.wlabel, "labels_plain": sorted(x for x in labs if x), "side": side,
               "entry_engine": float(r.entry), "entry_plain": float(e_px), "atr_engine": float(r.atr20), "atr_plain": atr,
               "exit_engine": float(r.exit), "exit_plain": float(x_px), "reason_engine": r.reason, "reason_plain": reason,
               "exit_time_engine": str(r.exit_time), "exit_time_plain": str(x_t), "swap_engine": float(r.swap), "swap_plain": float(swap),
               "nights_plain": nights, "R_engine": float(r.R), "R_plain": float(R)}
        ok = (chk["labels_plain"] == [r.wlabel] and abs(chk["entry_engine"] - e_px) < 1e-9 and abs(chk["atr_engine"] - atr) < 1e-6
              and abs(chk["exit_engine"] - x_px) < 1e-9 and chk["reason_engine"] == reason and chk["exit_time_engine"] == str(x_t)
              and abs(chk["swap_engine"] - swap) < 1e-9 and abs(chk["R_engine"] - R) < 1e-9)
        chk["match"] = bool(ok)
        worst = max(worst, abs(chk["R_engine"] - R))
        rows.append(chk)
    out = {"what": "independent recomputation of main trades from raw in-sample quotes", "n_checked": len(rows),
           "all_match": all(r["match"] for r in rows), "max_abs_R_diff": worst, "rows": rows}
    C.jdump(out, os.path.join(C.OUT, "handcheck.json"))
    print(out["n_checked"], "checked; all match:", out["all_match"], "max |dR|:", worst)
    for r in rows:
        if not r["match"]:
            print(r)


if __name__ == "__main__":
    main()
