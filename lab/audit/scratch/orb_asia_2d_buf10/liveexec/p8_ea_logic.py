"""P8: implementation choices an EA / a manual trader must make that the backtest fixes implicitly.
Each order's standalone trade is independent of the others (no compounding interaction), so the
'one position' policies are selection rules on the standalone trades (V4/V5 need re-simulation).
  V1 backtest: take the day's first touch only if flat at that moment          (must equal baseline)
  V2 arm the OCO pair at 07:00 London only if flat at 07:00 (no re-arming later that morning)
  V3 every signal (hedging account, overlapping positions allowed)
  V4 newest wins: a new signal closes any open position and opens the new one
  V5 reverse only: same-direction signal while in a position -> ignore; opposite -> close & reverse
  OCO  manual pending orders, opposite leg NOT cancelled after the fill (hedging account): when the
       first trade is stopped before 12:00 London, the other leg (same price) opens a 2nd position
Also: weekend exposure by schedule (Thu/Fri entries are held over a weekend if they survive).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(os.path.join(HERE, "orders_base.pkl")).sort_values("entry_i").reset_index(drop=True)
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
idx = m1.index
s, p = finalist_sessions(m1)
smap = s.set_index("date")
o["arm_i"] = smap.loc[pd.DatetimeIndex(o.date), "i1"].to_numpy()
o["ie"] = smap.loc[pd.DatetimeIndex(o.date), "ie"].to_numpy()
ind = gl.simulate(m1, o, no_overlap=False)          # every signal, standalone
ind = ind.loc[o.index.intersection(ind.index)].sort_index()
x_i = gl.entry_index(m1, ind.exit_time - pd.Timedelta(minutes=1) * (ind.reason != "time"))
ind["x_i"] = x_i
ind["entry_i"] = o.loc[ind.index, "entry_i"].to_numpy()
ind["arm_i"] = o.loc[ind.index, "arm_i"].to_numpy()


def select(rule):
    keep, last = [], -1
    for k, r in ind.iterrows():
        if rule == "V1" and r.entry_i > last:
            keep.append(k)
            last = r.x_i
        elif rule == "V2" and r.arm_i > last and r.entry_i > last:
            keep.append(k)
            last = r.x_i
    return ind.loc[keep]


V = {"V1_backtest_rule": select("V1"), "V2_arm_only_if_flat_at_0700": select("V2"), "V3_every_signal": ind}
# V4 newest wins
o4 = o.copy()
nxt = np.r_[o4.entry_i.to_numpy()[1:], np.iinfo(np.int64).max]
o4["exit_i"] = np.minimum(o4.exit_i.to_numpy(), nxt)
o4 = o4[o4.exit_i > o4.entry_i]
V["V4_newest_wins"] = gl.simulate(m1, o4, no_overlap=False)
# V5 reverse only
rows5, cur = [], None   # cur = [order_row_index, side, x_i]
o5 = o.copy()
for k in ind.index:
    r = ind.loc[k]
    if cur is None or r.entry_i > cur[2]:
        rows5.append(k)
        cur = [k, r.side, r.x_i]
    elif r.side == cur[1]:
        continue
    else:
        o5.loc[cur[0], "exit_i"] = min(o5.loc[cur[0], "exit_i"], r.entry_i)
        rows5.append(k)
        cur = [k, r.side, r.x_i]
o5 = o5.loc[rows5]
o5 = o5[o5.exit_i > o5.entry_i]
V["V5_reverse_only"] = gl.simulate(m1, o5, no_overlap=False)
# OCO leg not cancelled
tb = t.copy()
tb["ie"] = smap.loc[pd.DatetimeIndex(tb.date), "ie"].to_numpy()
tb["exit_i"] = smap.loc[pd.DatetimeIndex(tb.date), "ix"].to_numpy()
tb["xs_i"] = gl.entry_index(m1, tb.exit_time - pd.Timedelta(minutes=1))
two = tb[(tb.reason == "stop") & (tb.xs_i < tb.ie)]
lvl1 = o.set_index("date").loc[pd.DatetimeIndex(two.date), "level"].to_numpy()   # first leg's pending level
o2 = pd.DataFrame({"entry_i": two.xs_i.to_numpy(), "side": -two.side.to_numpy(), "etype": 1,
                   "level": two.stop.to_numpy(), "expiry_i": two.ie.to_numpy() - 1,
                   "stop": lvl1, "exit_i": two.exit_i.to_numpy(), "date": two.date.to_numpy()})
leg2 = gl.simulate(m1, o2, no_overlap=False)
V["OCO_leg2_only"] = leg2
V["OCO_not_cancelled_total"] = pd.concat([t, leg2])
frames = [v.assign(variant=k) for k, v in V.items()]
# weekend exposure by schedule
dow = t.entry_time.dt.tz_convert(gl.LDN).dt.dayofweek
frames.append(t[dow >= 3].assign(variant="sched_Thu_Fri_entries(weekend-exposed)"))
frames.append(t[dow < 3].assign(variant="sched_Mon_Wed_entries"))
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "EA position-policy variants V1-V5, un-cancelled OCO leg, weekend schedule split")
rows = []
for k in allt.variant.unique():
    a, b = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, "IS_n": a["n"], "IS_pf": a["pf"], "IS_t": a["t"], "IS_yrs": a.get("yrs_pos"),
                 "IS_pfL": a.get("pf_long"), "IS_pfS": a.get("pf_short"),
                 "VAL_n": b["n"], "VAL_pf": b["pf"], "VAL_t": b["t"], "VAL_pfL": b.get("pf_long"), "VAL_pfS": b.get("pf_short")})
r = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(r.to_string(index=False))
r.to_csv(os.path.join(HERE, "p8_ea_logic.csv"), index=False)
v1 = V["V1_backtest_rule"]
print("V1 reproduces baseline:", len(v1) == len(t) and np.allclose(np.sort(v1.R.to_numpy()), np.sort(t.R.to_numpy())))
print("OCO: sessions where the 1st trade is stopped before 12:00 London:", len(two), "of", len(t),
      "| 2nd legs filled:", len(leg2), "| 2nd-leg stop exits:", int((leg2.reason == "stop").sum()))
