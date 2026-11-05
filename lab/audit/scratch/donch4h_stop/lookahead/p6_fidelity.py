"""P6: execution-fidelity probes.
 A. refimpl2 variants (IS + VAL, one logged cut): tick-calibrated fast-market fills, trailing
    granularity (intrabar/tick-like, MT5-built-in-like), decisions only when a French retail
    trader is awake (alerts-first execution).
 B. engine trades (IS; VAL through one logged cut): news-minute fills, first-bar (market-like)
    fills, OCO ties over all windows, Friday-triple swap convention, lot-step rounding."""
import json
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
sys.path.insert(0, "audit/scratch/donch4h_stop/lookahead")
import numpy as np
import pandas as pd

import goldlab as gl
import refimpl as RI
import refimpl2 as R2
import strategy as S

T0 = time.time()
t, c = RI.load_raw()
OUT = {}


def hours_utc(dec_ns):
    return pd.to_datetime(dec_ns, utc=True).hour.to_numpy()


variants = {
    "base": {},
    "calib_fills_noslip": {"ffrac_in": 0.09, "ffrac_out": 0.21, "slip_bps": 0.0},
    "calib_fills_plus_slip": {"ffrac_in": 0.09, "ffrac_out": 0.21},
    "trail_intrabar_tick_like": {"trail_mode": 1},
    "trail_mt5_builtin_like": {"trail_mode": 2},
    "skip_00_04utc_decisions": {"dec_filter": lambda d: ~np.isin(hours_utc(d), [0, 4])},
    "only_16_20utc_decisions": {"dec_filter": lambda d: np.isin(hours_utc(d), [16, 20])},
}
frames = []
for lab, kw in variants.items():
    tr = R2.run(t, c, **kw)
    tr["variant"] = lab
    frames.append(tr)
allf = pd.concat(frames, ignore_index=True)
is_ = allf[(allf.entry_time >= pd.Timestamp("2013-01-01", tz="UTC")) & (allf.entry_time < pd.Timestamp("2022-01-01", tz="UTC"))]
val = gl.cut(allf, "val", track="review", label="lookahead:donch4h_stop:execution-fidelity")
print("== A. execution variants")
for lab in variants:
    r = {"is": R2.stats(is_[is_.variant == lab]), "val": R2.stats(val[val.variant == lab])}
    OUT[lab] = r
    print(f"  {lab:28s} IS {r['is']}\n  {'':28s} VAL {r['val']}")
assert OUT["base"]["is"]["pf"] == 1.35 and OUT["base"]["val"]["pf"] == 1.294

# ---------------------------------------------------------------- B. engine trades
m1 = gl.load_m1("xauusd")
P = S.FINALISTS["donch4h_stop"]
orders = S.make_orders(m1, **P)
eng = gl.simulate(m1, orders)
e_is = gl.cut(eng, "is")
e_val = gl.cut(eng, "val", track="review", label="lookahead:donch4h_stop:engine-trade-breakdowns")


def pf(R):
    R = np.asarray(R)
    return round(float(R[R > 0].sum() / -R[R < 0].sum()), 3) if (R < 0).any() else float("nan")


print("\n== B1. news minutes (NY 08:30-08:34, 10:00-10:04, 14:00-14:04, 14:30-14:34)")
for name, tt in (("IS", e_is), ("VAL", e_val)):
    ny_in = gl.local(tt.entry_time, gl.NY)
    ny_out = gl.local(tt.exit_time - pd.Timedelta(minutes=1), gl.NY)

    def news(x):
        m = x.hour * 60 + x.minute
        return np.isin(m // 1, [8 * 60 + 30 + k for k in range(5)] + [10 * 60 + k for k in range(5)]
                       + [14 * 60 + k for k in range(5)] + [14 * 60 + 30 + k for k in range(5)])
    ne, nx = news(ny_in), news(ny_out)
    print(f"  {name}: entries in news minutes {ne.sum()}/{len(tt)} (R {tt.R[ne].sum():+.1f}); exits in news minutes"
          f" {nx.sum()} (R {tt.R[nx].sum():+.1f}); PF without news-entry trades {pf(tt.R[~ne])} (all {pf(tt.R)})")
    OUT[f"news_{name}"] = {"entries": int(ne.sum()), "entries_R": round(float(tt.R[ne].sum()), 1),
                           "exits": int(nx.sum()), "exits_R": round(float(tt.R[nx].sum()), 1),
                           "pf_without_news_entries": pf(tt.R[~ne])}

print("\n== B2. first-bar fills (order filled in the first M1 bar after the 4h close)")
for name, tt in (("IS", e_is), ("VAL", e_val)):
    oo = orders.loc[tt.index]
    first = (oo.trig_i.to_numpy() == oo.entry_i.to_numpy())
    fi = oo.trig_i.to_numpy()
    gap = np.where(oo.side > 0, m1.ao.to_numpy()[fi] >= oo.level.to_numpy(), m1.bo.to_numpy()[fi] <= oo.level.to_numpy())
    print(f"  {name}: first-bar fills {first.sum()}/{len(tt)} (R {tt.R[first].sum():+.1f}); of which opened beyond the level "
          f"(market-like) {int((first & gap).sum())}; all gap fills {int(gap.sum())} (R {tt.R[gap].sum():+.1f})")
    OUT[f"firstbar_{name}"] = {"first_bar": int(first.sum()), "first_bar_R": round(float(tt.R[first].sum()), 1),
                               "gap_fills": int(gap.sum()), "gap_R": round(float(tt.R[gap].sum()), 1)}

print("\n== B3. OCO: both levels inside the first-touch M1 bar, over ALL resolved windows")
S._bar_cache.clear()
b = S.bars_cached(m1, "4h")
up = b["h"].rolling(60).max().to_numpy()
dn = b["l"].rolling(60).min().to_numpy()
pos = pd.DatetimeIndex(b["t_close"]).get_indexer(orders.dec_time)
fi = orders.trig_i.to_numpy()
both = (m1.ah.to_numpy()[fi] >= up[pos]) & (m1.bl.to_numpy()[fi] <= dn[pos])
print(f"  windows {len(orders)}, ties {int(both.sum())}")
OUT["oco_ties_all_windows"] = int(both.sum())

print("\n== B4. swap convention: triple on Friday instead of Wednesday")
for name, tt in (("IS", e_is), ("VAL", e_val)):
    d0 = gl.trading_day(tt.entry_time).values.astype("datetime64[D]")
    d1 = gl.trading_day(tt.exit_time - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    n_wed = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask="Wed")
    n_fri = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask="Fri")
    rate = np.where(tt.side > 0, 0.05, 0.02)
    R_fri = tt.R - tt.entry * rate / 360 * (n_fri - n_wed) / tt.risk
    print(f"  {name}: PF Wed-triple {pf(tt.R)} -> Fri-triple {pf(R_fri)}")
    OUT[f"swap_fri_{name}"] = pf(R_fri)

print("\n== B5. lot-step rounding (1 oz = 0.01 lot), 1% risk per trade, min size 1 oz, equity compounding")
for name, tt in (("IS", e_is), ("VAL", e_val)):
    tt = tt.sort_values("entry_time")
    res = {}
    for eq0 in (2_000, 5_000, 10_000, 25_000, 100_000):
        eq = float(eq0)
        pl = []
        for pnl, risk in zip(tt.pnl.to_numpy(), tt.risk.to_numpy()):
            oz = max(1.0, round(eq * 0.01 / risk))
            pl.append(pnl * oz)
            eq += pnl * oz
        pl = np.array(pl)
        res[eq0] = pf(pl)
    print(f"  {name}: PF in $ by starting equity {res}  (PF in R {pf(tt.R)}, equal-size {pf(tt.pnl)})")
    OUT[f"lots_{name}"] = {str(k): v for k, v in res.items()}
json.dump(OUT, open("audit/scratch/donch4h_stop/lookahead/p6_fidelity.json", "w"), indent=1)
print(f"time {time.time()-T0:.0f}s")
