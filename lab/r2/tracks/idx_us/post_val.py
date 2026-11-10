"""After the single validation: account-feasibility numbers that need 2024-2025 prices but no P&L
(stop distance of the ORDERS, not of simulated trades), and warm-up parity on a short frame."""
from harness import *     # noqa
out = {}
m1 = r2.load("us100")
idx = m1.index
ao, bo = m1["ao"].to_numpy(), m1["bo"].to_numpy()
spec = r2.SPEC["us100"]
for name, f in S.FINALISTS.items():
    o = S.make_orders(m1, **f["params"])
    t = idx[o.entry_i.to_numpy()]
    fill = np.where(o.side.to_numpy() > 0, ao[o.entry_i.to_numpy()], bo[o.entry_i.to_numpy()])
    dist = np.where(o["stop"].notna().to_numpy(), np.abs(fill - o["stop"].to_numpy()), o["stop_dist"].to_numpy())
    sel = (t >= pd.Timestamp("2024-01-01", tz="UTC")) & (t < pd.Timestamp("2026-01-01", tz="UTC"))
    d = pd.Series(dist[sel])
    px = pd.Series(fill[sel])
    lot_units = spec["min_lot"] * spec["units_per_lot"]
    out[name] = {"sym": "us100", "orders_2024_2025": int(sel.sum()), "median_stop_points": round(float(d.median()), 1),
                 "p10_stop_points": round(float(d.quantile(0.1)), 1), "p90_stop_points": round(float(d.quantile(0.9)), 1),
                 "median_stop_bp": round(float((d / px).median() * 1e4), 1), "median_price": round(float(px.median()), 0),
                 "min_lot": spec["min_lot"], "units_per_lot": spec["units_per_lot"],
                 "min_lot_stop_money_usd": round(float(d.median() * lot_units), 2),
                 "min_lot_stop_money_usd_p90": round(float(d.quantile(0.9) * lot_units), 2),
                 "min_lot_notional_usd": round(float(px.median() * lot_units), 0),
                 "min_lot_margin_usd_at_1:200": round(float(px.median() * lot_units / spec["leverage"]), 2)}
    print(name, out[name])
# warm-up parity: orders built on a frame that starts 2021-09-01 vs the full frame, for entries from 2021-11-01
start = pd.Timestamp("2021-09-01", tz="UTC"); cutoff = pd.Timestamp("2021-11-01", tz="UTC"); end = pd.Timestamp("2022-01-01", tz="UTC")
lo = int(idx.searchsorted(start)); hi = int(idx.searchsorted(end))
ms = m1.iloc[lo:hi]
par = {}
for name, f in S.FINALISTS.items():
    of = S.make_orders(m1, **f["params"]); os_ = S.make_orders(ms, **f["params"])
    a = of[(idx[of.entry_i.to_numpy()] >= cutoff) & (idx[of.entry_i.to_numpy()] < end)].reset_index(drop=True)
    b = os_[ms.index[os_.entry_i.to_numpy()] >= cutoff].reset_index(drop=True)
    same = len(a) == len(b) and bool((a.entry_i.to_numpy() - lo == b.entry_i.to_numpy()).all()) and bool((a.side.to_numpy() == b.side.to_numpy()).all()) \
        and bool(np.allclose(a["stop"].fillna(0), b["stop"].fillna(0))) and bool(np.allclose(a.stop_dist.fillna(0), b.stop_dist.fillna(0))) \
        and bool((a.exit_i.to_numpy() - lo == b.exit_i.to_numpy()).all())
    par[name] = {"orders_full_frame": int(len(a)), "orders_short_frame": int(len(b)), "identical_after_2_months_warmup": same}
    print("warm-up parity", name, par[name])
out["warmup_parity_2021-09-01_start"] = par
json.dump(out, open(os.path.join(RES, "account_feasibility.json"), "w"), indent=1, default=str)
