"""P6: quantified MT5 pitfalls on the baseline path.
 a stop fills beyond the stop (weekend / daily-break / intrasession gaps) and their cost in R
 b weekend-held trades; holiday time exits (16:00 NY bar missing)
 c distance from market to each pending level when the OCO pair is placed (StopsLevel / FreezeLevel)
 d range data completeness (M1 bars present out of 420) and min_bars_frac sensitivity
 e fills near the 12:00 London expiry
 f retail cost add-ons: extra fixed $/oz per round trip, retail swap rates
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403
from common import _pf

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(os.path.join(HERE, "orders_base.pkl"))
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
idx = m1.index
slip = COSTS["xauusd"].slip_bps * 1e-4
# ---- a. gap fills
st = t[t.reason == "stop"].copy()
xi = gl.entry_index(m1, st.exit_time - pd.Timedelta(minutes=1))
prev_gap = (idx[xi] - idx[np.maximum(xi - 1, 0)]).total_seconds() / 60
raw_x = np.where(st.side > 0, st.exit / (1 - slip), st.exit / (1 + slip))
beyond = st.side * (st.stop - raw_x) / st.risk          # R lost beyond the stop price (before slippage)
st["beyond_R"] = beyond.to_numpy()
st["gap_min"] = prev_gap
st["kind"] = np.where(prev_gap > 24 * 60, "weekend/holiday", np.where(prev_gap >= 55, "daily_break", "intrasession"))
g = st[st.beyond_R > 0.01]
print("a) stop exits:", len(st), "| filled beyond stop by >0.01R:", len(g),
      "| by kind:", g.kind.value_counts().to_dict(),
      "| sum extra R:", round(float(g.beyond_R.sum()), 2), "| worst R:", round(float(st.R.min()), 2),
      "| R < -1.25:", int((st.R < -1.25).sum()))
print("   worst 5 gap fills:", g.sort_values("beyond_R", ascending=False).head(5)[["entry_time", "exit_time", "side", "R", "beyond_R", "kind"]].to_string())
# ---- b. weekend / holidays
ed = t.entry_time.dt.tz_convert(gl.LDN).dt.dayofweek
wk = t.exit_time.dt.tz_convert(gl.NY).dt.normalize() - t.entry_time.dt.tz_convert(gl.NY).dt.normalize() > pd.Timedelta(days=2)
held_weekend = (t.exit_time.dt.tz_convert(None).dt.to_period("W") != t.entry_time.dt.tz_convert(None).dt.to_period("W"))
print("b) trades held over a weekend:", int(held_weekend.sum()), "of", len(t), "| entry weekday counts:", ed.value_counts().sort_index().to_dict())
ti = is_part(t.assign(wkend=held_weekend.to_numpy()))
tv = val_part(t.assign(wkend=held_weekend.to_numpy()), "pitfalls: weekend-held vs not, gap fills, holiday exits")
for nm, part in (("IS", ti), ("VAL", tv)):
    print(f"   {nm}: weekend-held PF {stats(part[part.wkend])['pf']} (n {int(part.wkend.sum())}) | not held PF {stats(part[~part.wkend])['pf']}")
xt = t[t.reason == "time"]
xn = xt.exit_time.dt.tz_convert(gl.NY)
hol = xt[(xn.dt.hour != 16) | (xn.dt.minute != 0)]
print("   time exits NOT at 16:00 NY (early close / holiday -> next open):", len(hol), "| their R sum", round(float(hol.R.sum()), 1),
      "| NY clock:", hol.exit_time.dt.tz_convert(gl.NY).dt.strftime("%a %H:%M").value_counts().head(6).to_dict())
# ---- c. distance to market at placement (first bar after the range = 07:00 London)
s, p = finalist_sessions(m1)
i1 = s.i1.to_numpy()
buf = p["buf_frac"] * s.width.to_numpy()
buy, sell = s.hi.to_numpy() + buf, s.lo.to_numpy() - buf
ask0, bid0 = m1.ao.to_numpy()[i1], m1.bo.to_numpy()[i1]
d_buy, d_sell = buy - ask0, bid0 - sell
dmin = np.minimum(d_buy, d_sell)
yrs = s.date.dt.year.to_numpy()
spr0 = (m1.ao - m1.bo).to_numpy()[i1]
for lab, sel in (("IS", yrs <= 2021), ("2025", yrs == 2025)):
    print(f"c) {lab}: nearer pending level vs market at 07:00 London, $: p1 {np.percentile(dmin[sel], 1):.2f} p5 {np.percentile(dmin[sel], 5):.2f} "
          f"p50 {np.median(dmin[sel]):.2f} | share < $0.30: {np.mean(dmin[sel] < .3):.3f}  < $0.50: {np.mean(dmin[sel] < .5):.3f}  "
          f"< $1.00: {np.mean(dmin[sel] < 1):.3f} | already through a level at 07:00: {int((dmin[sel] <= 0).sum())} "
          f"| spread at 07:00 median ${np.median(spr0[sel]):.2f} p95 ${np.percentile(spr0[sel], 95):.2f} | SL distance (1.2W) p1 ${np.percentile(1.2 * s.width.to_numpy()[sel], 1):.2f}")
# ---- d. data completeness of the range
nb = s.nbars.to_numpy()
print("d) range M1 bars present (of 420): p1", int(np.percentile(nb, 1)), "p5", int(np.percentile(nb, 5)), "median", int(np.median(nb)),
      "| sessions <90%:", int((nb < 378).sum()), "<75%:", int((nb < 315).sum()), "of", len(nb))
alls, _ = finalist_sessions(m1, min_bars_frac=0.0)
print("   sessions dropped by min_bars_frac=0.5:", len(alls) - len(s))
fr = []
for mbf in (0.5, 0.9, 0.97):
    oo = S.make_orders(m1, **{**PARAMS, "min_bars_frac": mbf})
    tt = gl.simulate(m1, oo, no_overlap=True)
    fr.append(tt.assign(variant=f"min_bars_frac={mbf}"))
# ---- e. fills near expiry
tl = t.entry_time.dt.tz_convert(gl.LDN)
mins = tl.dt.hour * 60 + tl.dt.minute
print("e) fills in the last 15 / 30 min before 12:00 London:", int((mins >= 705).sum()), "/", int((mins >= 690).sum()), "of", len(t))
# ---- f. retail costs (post-hoc on the baseline path)
alltt = pd.concat(fr)
fi_ = is_part(alltt)
fv_ = val_part(alltt, "pitfalls: min_bars_frac 0.5/0.9/0.97 data-completeness guard")
for k in alltt.variant.unique():
    print(f"   {k}: IS {fmt(stats(fi_[fi_.variant == k]))}\n        VAL {fmt(stats(fv_[fv_.variant == k]))}")
rows = []
for extra in (0.0, 0.10, 0.25, 0.50, 1.00):
    for sw in ((0.05, 0.02), (0.08, 0.02), (0.10, 0.04)):
        c = Costs(swap_long=sw[0], swap_short=sw[1])
        tt = post_costs(t, c)
        tt["R"] = (tt.pnl - extra) / tt.risk
        a, b = is_part(tt), tt[(tt.entry_time >= pd.Timestamp("2022-01-01", tz="UTC"))]
        rows.append((extra, sw, a, b))
tvv = val_part(pd.concat([r[3].assign(extra=r[0], sw=str(r[1])) for r in rows]), "retail add-on costs: extra $/oz RT x swap rates")
print("f) extra round-trip cost $/oz x swap (long,short)/yr -> IS PF | VAL PF")
for extra, sw, a, _ in rows:
    b = tvv[(tvv.extra == extra) & (tvv.sw == str(sw))]
    print(f"   +${extra:.2f}  swap {sw}:  IS {stats(a)['pf']}  (t {stats(a)['t']})  | VAL {stats(b)['pf']}  (t {stats(b)['t']})")
cost_now = (t.swap + t.commission).mean()
print("   mean swap+commission per trade $/oz:", round(float(cost_now), 3), "| mean swap long", round(float(t[t.side > 0].swap.mean()), 3),
      "short", round(float(t[t.side < 0].swap.mean()), 3), "| mean nights", round(float(post_costs(t).nights.mean()), 2))
