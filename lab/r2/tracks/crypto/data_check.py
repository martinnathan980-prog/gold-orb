"""Data sanity check for btcusd / ethusd (FP-cost frames). Descriptive only, no trading rule."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/gold-orb/lab")
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

OUT = "/home/user/gold-orb/lab/results/r2/crypto"
res = {}
for sym in ("btcusd", "ethusd"):
    m1 = r2.load(sym)
    idx = m1.index
    mid = (m1.bc + m1.ac) / 2
    spr = (m1.ac - m1.bc)
    d = {"first": str(idx[0]), "last": str(idx[-1]), "n": int(len(m1)), "dtype": str(idx.dtype)}
    # bars per calendar day (UTC)
    day = idx.tz_convert("UTC").normalize()
    cnt = pd.Series(1, index=day).groupby(level=0).sum()
    full = pd.date_range(cnt.index.min(), cnt.index.max(), freq="D")
    cnt = cnt.reindex(full, fill_value=0)
    d["days_total"] = int(len(cnt))
    d["days_missing"] = int((cnt == 0).sum())
    d["days_lt_720"] = int((cnt < 720).sum())
    dow = cnt.groupby(cnt.index.dayofweek).median()
    d["median_bars_by_dow(Mon=0)"] = {int(k): float(v) for k, v in dow.items()}
    by_year = cnt.groupby(cnt.index.year).agg(["median", "min", "mean"])
    d["bars_per_day_by_year"] = {int(y): {"median": float(r["median"]), "min": float(r["min"]), "mean": round(float(r["mean"]), 1)} for y, r in by_year.iterrows()}
    d["missing_days_by_year"] = {int(y): int(v) for y, v in (cnt == 0).groupby(cnt.index.year).sum().items()}
    d["short_days_by_year(<720)"] = {int(y): int(v) for y, v in (cnt < 720).groupby(cnt.index.year).sum().items()}
    # weekend presence: share of Saturday / Sunday days with > 720 bars, by year
    we = cnt[cnt.index.dayofweek >= 5]
    d["weekend_days_with_data_pct_by_year"] = {int(y): round(float(v) * 100, 1) for y, v in (we > 720).groupby(we.index.year).mean().items()}
    # gaps
    dt = np.diff(idx.values).astype("timedelta64[m]").astype(np.int64)
    gi = np.where(dt > 60)[0]
    gaps = pd.DataFrame({"start": idx[gi], "end": idx[gi + 1], "minutes": dt[gi]})
    d["gaps_gt_60min"] = int(len(gaps))
    d["gaps_gt_60min_by_year"] = {int(y): int(v) for y, v in gaps.groupby(gaps.start.dt.year).size().items()}
    gaps["dow"] = gaps.start.dt.dayofweek
    gaps["hour"] = gaps.start.dt.hour
    d["gap_start_dow_hour_top"] = {f"{int(a)}-{int(b)}": int(v) for (a, b), v in gaps.groupby(["dow", "hour"]).size().sort_values(ascending=False).head(12).items()}
    d["gap_minutes_quantiles"] = {str(q): float(gaps.minutes.quantile(q)) for q in (0.5, 0.9, 0.99, 1.0)}
    d["largest_gaps"] = [[str(r.start), str(r.end), int(r.minutes)] for r in gaps.sort_values("minutes", ascending=False).head(12).itertuples()]
    gaps.to_csv(os.path.join(OUT, f"data_gaps_{sym}.csv"), index=False)
    # small gaps (2..60 min): how gappy is the minute stream
    d["share_minutes_present_by_year"] = {}
    for y, c in cnt.groupby(cnt.index.year):
        d["share_minutes_present_by_year"][int(y)] = round(float(c.sum() / (len(c) * 1440)), 3)
    # crazy prints: 1-minute mid return, bar range vs price
    r1 = mid.pct_change().abs()
    rng = ((m1.ah + m1.bh) / 2 - (m1.al + m1.bl) / 2) / mid
    d["abs_1m_ret_quantiles_bp"] = {str(q): round(float(r1.quantile(q) * 1e4), 1) for q in (0.5, 0.99, 0.999, 0.9999, 1.0)}
    d["bar_range_quantiles_bp"] = {str(q): round(float(rng.quantile(q) * 1e4), 1) for q in (0.5, 0.99, 0.999, 0.9999, 1.0)}
    big = r1[r1 > 0.05]
    d["n_1m_moves_gt_5pct"] = int(len(big))
    d["biggest_1m_moves"] = [[str(t), round(float(v) * 100, 2), int((dt[idx.get_loc(t) - 1]) if idx.get_loc(t) > 0 else 0)] for t, v in r1.sort_values(ascending=False).head(15).items()]
    # spike-and-revert prints: bar whose high/low exceeds both neighbours' closes by > 3 %
    hi = (m1.ah + m1.bh) / 2
    lo = (m1.al + m1.bl) / 2
    prev_c, next_c = mid.shift(1), mid.shift(-1)
    spike_up = (hi / np.maximum(prev_c, next_c) - 1) > 0.03
    spike_dn = (1 - lo / np.minimum(prev_c, next_c)) > 0.03
    d["spike_bars_gt_3pct"] = int((spike_up | spike_dn).sum())
    d["spike_bars_by_year"] = {int(y): int(v) for y, v in (spike_up | spike_dn).groupby(idx.year).sum().items()}
    d["spike_examples"] = [str(t) for t in idx[(spike_up | spike_dn).to_numpy()][:15]]
    # ohlc consistency
    bad = (m1.bh < m1.bl) | (m1.bh < m1.bo) | (m1.bh < m1.bc) | (m1.bl > m1.bo) | (m1.bl > m1.bc) | (m1.ac < m1.bc)
    d["ohlc_inconsistent"] = int(bad.sum())
    d["nan_rows"] = int(m1.isna().any(axis=1).sum())
    # modelled spread in bp by year, by hour (UTC)
    sb = spr / mid * 1e4
    d["fp_spread_bp_by_year_median"] = {int(y): round(float(v), 2) for y, v in sb.groupby(idx.year).median().items()}
    d["fp_spread_bp_by_year_mean"] = {int(y): round(float(v), 2) for y, v in sb.groupby(idx.year).mean().items()}
    d["fp_spread_bp_by_hour_utc_mean"] = {int(h): round(float(v), 2) for h, v in sb.groupby(idx.hour).mean().items()}
    d["fp_spread_bp_quantiles"] = {str(q): round(float(sb.quantile(q)), 2) for q in (0.01, 0.5, 0.9, 0.99, 0.999, 1.0)}
    # price level & hourly vol by year
    h1 = mid.resample("1h").last().dropna()
    hr = np.log(h1).diff().dropna()
    d["price_by_year_mean"] = {int(y): round(float(v), 1) for y, v in mid.groupby(idx.year).mean().items()}
    d["hourly_abs_ret_bp_by_year_median"] = {int(y): round(float(v) * 1e4, 1) for y, v in hr.abs().groupby(hr.index.year).median().items()}
    d["hourly_ret_std_bp_by_year"] = {int(y): round(float(v) * 1e4, 1) for y, v in hr.groupby(hr.index.year).std().items()}
    d["year_return_pct"] = {int(y): round(float((g.iloc[-1] / g.iloc[0] - 1) * 100), 1) for y, g in mid.groupby(idx.year)}
    res[sym] = d
    r2.free()
    del m1

# raw Dukascopy spread (for information: historical real cost), only closes
for sym in ("btcusd", "ethusd"):
    raw = pd.read_parquet(os.path.join(gl.data.DATA, f"{sym}_m1.parquet"), columns=["bc", "ac"])
    raw = raw[raw.index < pd.Timestamp("2026-01-01", tz="UTC")]
    sb = (raw.ac - raw.bc) / ((raw.ac + raw.bc) / 2) * 1e4
    res[sym]["dukascopy_spread_bp_by_year_median"] = {int(y): round(float(v), 2) for y, v in sb.groupby(raw.index.year).median().items()}
    del raw

json.dump(res, open(os.path.join(OUT, "data_check.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
