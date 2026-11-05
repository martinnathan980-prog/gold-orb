"""P2: hand-check a random sample of IS trades against RAW M1 rows (pandas slicing by timestamp,
no goldlab / refimpl code): channel, ATR, OCO first touch, fill, trailing path, exit, swap, R."""
import sys

sys.path.insert(0, ".")
import numpy as np
import pandas as pd

OUT = "audit/scratch/donch4h_stop/lookahead"
raw = pd.read_parquet("data/xauusd_m1.parquet")
tr = pd.read_pickle(f"{OUT}/trades_is_base.pkl")          # engine IS trades (from p0)
rng = np.random.default_rng(20261105)
sample = tr.iloc[np.sort(rng.choice(len(tr), 14, replace=False))]
SLIP = 1.5e-4
H4 = pd.Timedelta(hours=4)
NY = "America/New_York"
rows = []
for k, (ix, x) in enumerate(sample.iterrows()):
    dec = x.dec_time                                   # engine decision time (bar close)
    bin_start = dec.floor("4h") if dec != dec.floor("4h") else dec - H4
    # ---- 4h bins: 900 calendar bins (~640 non-empty) of history before the decision (for ATR convergence) ----
    hist = raw[(raw.index >= bin_start - 900 * H4) & (raw.index < bin_start + H4)]
    g = hist.groupby(hist.index.floor("4h"))
    hb = pd.DataFrame({"h": (g.bh.max() + g.ah.max()) / 2, "l": (g.bl.min() + g.al.min()) / 2,
                       "c": (g.bc.last() + g.ac.last()) / 2})
    assert hb.index[-1] == bin_start, (hb.index[-1], bin_start)
    last60 = hb.iloc[-60:]
    up, dn = last60.h.max(), last60.l.min()
    pc = hb.c.shift(1)
    trr = pd.concat([hb.h - hb.l, (hb.h - pc).abs(), (hb.l - pc).abs()], axis=1).max(axis=1)
    atr = trr.iloc[1:].ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    # ---- the OCO window: from the first bar after the decision to the end of the next non-empty bin
    after = raw[raw.index >= dec]
    nxt_bin = after.index[0].floor("4h")
    win = after[after.index < nxt_bin + H4]
    hit_up = win.index[win.ah >= up]
    hit_dn = win.index[win.bl <= dn]
    first_up = hit_up[0] if len(hit_up) else None
    first_dn = hit_dn[0] if len(hit_dn) else None
    cands = [v for v in (first_up, first_dn) if v is not None]
    ft = min(cands)
    side = 1 if (first_up is not None and first_up == ft and (first_dn is None or first_dn > ft)) else -1
    fb = raw.loc[ft]
    fp = max(up, fb.ao) * (1 + SLIP) if side > 0 else min(dn, fb.bo) * (1 - SLIP)
    # ---- trailing path on raw rows from the fill bar ----
    stop0 = fp - side * 2 * atr
    path = raw[(raw.index >= ft) & (raw.index <= x.exit_time + pd.Timedelta(minutes=1))]
    cur, best, ex_t, ex_px, why = stop0, fp, None, None, None
    tx = (pd.Timestamp(dec).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7) + pd.offsets.BDay(5)
          - pd.Timedelta(hours=7) - pd.Timedelta(minutes=5)).tz_localize(NY).tz_convert("UTC")
    for i, (ts, r) in enumerate(path.iterrows()):
        if ts >= tx and i > 0:
            ex_t, ex_px, why = ts, (r.bo * (1 - SLIP) if side > 0 else r.ao * (1 + SLIP)), "time"
            break
        if side > 0:
            if r.bl <= cur:
                ex_t, ex_px, why = ts + pd.Timedelta(minutes=1), (cur if i == 0 else min(cur, r.bo)) * (1 - SLIP), "stop/trail"
                break
            best = max(best, r.bh)
            cur = max(cur, best - 2 * atr)
        else:
            if r.ah >= cur:
                ex_t, ex_px, why = ts + pd.Timedelta(minutes=1), (cur if i == 0 else max(cur, r.ao)) * (1 + SLIP), "stop/trail"
                break
            best = min(best, r.al)
            cur = min(cur, best + 2 * atr)
    # swap nights: 17:00 NY rollovers between entry and exit, Wed x3
    a_ny, b_ny = ft.tz_convert(NY), ex_t.tz_convert(NY)
    nights = 0
    d = a_ny.normalize()
    while d <= b_ny.normalize():
        ro = d + pd.Timedelta(hours=17)
        if a_ny < ro < b_ny and ro.dayofweek < 5:
            nights += 3 if ro.dayofweek == 2 else 1
        d += pd.Timedelta(days=1)
    swap = fp * (0.05 if side > 0 else 0.02) / 360 * nights
    pnl = side * (ex_px - fp) - swap - 0.07
    R = pnl / (2 * atr)
    diffs = dict(side=side - x.side, fp=fp - x.entry, ft=ft == x.entry_time, ex_t=ex_t == x.exit_time, ex_px=ex_px - x.exit, R=R - x.R, risk=2 * atr - (x.entry - x.stop) * x.side)
    ok = (side == x.side and abs(fp - x.entry) < 1e-6 and ft == x.entry_time and ex_t == x.exit_time
          and abs(ex_px - x.exit) < 1e-6 and abs(R - x.R) < 1e-6 and abs(2 * atr * 1 - (x.entry - x.stop) * x.side) < 1e-6)
    rows.append({"dec_utc": dec, "side": side, "up": round(up, 3), "dn": round(dn, 3), "atr": round(atr, 4),
                 "fill_bar": ft, "fill_px": round(fp, 3), "exit_t": ex_t, "exit_px": round(ex_px, 3), "why": why,
                 "nights": nights, "R_hand": round(R, 4), "R_engine": round(x.R, 4), "match": ok,
                 "max_abs_diff": max(abs(diffs["fp"]), abs(diffs["ex_px"]), abs(diffs["R"]), abs(diffs["risk"]))})
    if not ok: print("DIFFS", diffs)
    if k < 3:   # print raw evidence rows for the first three trades
        print(f"\n--- trade {k}: decision {dec} (bin {bin_start}), channel up={up:.3f} dn={dn:.3f} ATR={atr:.4f}")
        print("  window rows up to and incl. the fill bar (bo ah bl ao):")
        print(win.loc[:ft, ["bo", "bh", "bl", "ao", "ah", "al"]].tail(4).round(3).to_string())
        print(f"  first ask-high>=up: {first_up}  first bid-low<=dn: {first_dn}  -> side {side}, fill {fp:.3f}")
        print("  exit bar rows:")
        print(raw.loc[ex_t - pd.Timedelta(minutes=3): ex_t, ["bo", "bh", "bl", "ao", "ah", "al"]].round(3).to_string())
        print(f"  stop at exit {cur:.3f} best {best:.3f} -> exit {ex_px:.3f} ({why}), nights {nights}, R {R:.4f} vs engine {x.R:.4f}")
res = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print("\n", res.to_string())
print("all match:", bool(res.match.all()), f"({res.match.sum()}/{len(res)})")
