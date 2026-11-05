"""P2: human availability.
(a) Paris clock of every signal (first touch) and of every time exit.
(b) Entry-availability subsets (re-simulated with the one-position rule on the subset):
    W0 any day 07-23 Paris | W1 weekdays 08-20 Paris | W2 pre-work 08-09 | W3 lunch 12-13 | W4 = W2+W3
    W5 'employee': W2/W3 signals at touch+1 min, 09-12 signals at market at 12:00 Paris (same distance)
(c) Exit availability: the 16:00 NY time exit is 22:00 Paris (21:00 in US/EU DST-gap weeks).
    E1 exit at 20:00 Paris same day | E2 exit next business day 08:00 Paris | E3 W1 entries + E1 exits
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(os.path.join(HERE, "orders_base.pkl"))
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
idx = m1.index
fi = o.entry_i.to_numpy()
tp = idx[fi].tz_convert(PARIS)
hp = tp.hour + tp.minute / 60
dow = tp.dayofweek
dist = (o.level - o.stop).abs().to_numpy()

print("signals (all touches) by Paris hour:", pd.Series(tp.hour).value_counts().sort_index().to_dict())
print("signals outside 07-23 Paris:", int(((hp < 7) | (hp >= 23)).sum()), "| outside weekdays 08-20:",
      int(((hp < 8) | (hp >= 20) | (dow >= 5)).sum()), "of", len(o))
xp = t[t.reason == "time"].exit_time.dt.tz_convert(PARIS)
print("time exits by Paris clock:", xp.dt.strftime("%H:%M").value_counts().head(6).to_dict())
xs = t[t.reason == "stop"].exit_time.dt.tz_convert(PARIS)
print("stop exits by Paris hour (share):", (xs.dt.hour.value_counts(normalize=True).sort_index().round(3)).to_dict())
print("stop exits on Sat/Sun Paris or Mon before 08:00 Paris (weekend gap fills):",
      int(((xs.dt.dayofweek >= 5) | ((xs.dt.dayofweek == 0) & (xs.dt.hour < 8))).sum()))


def mk_market(sel, ei, stop_dist):
    return pd.DataFrame({"entry_i": ei[sel], "side": o.side.to_numpy()[sel], "etype": 0, "stop": np.nan,
                         "stop_dist": stop_dist[sel], "exit_i": o.exit_i.to_numpy()[sel], "date": o.date.to_numpy()[sel]})


variants = {}
w = {"W0_any_07-23": (hp >= 7) & (hp < 23), "W1_wkday_08-20": (hp >= 8) & (hp < 20) & (dow < 5),
     "W2_prework_08-09": (hp >= 8) & (hp < 9), "W3_lunch_12-13": (hp >= 12) & (hp < 13),
     "W4_pre+lunch": ((hp >= 8) & (hp < 9)) | ((hp >= 12) & (hp < 13))}
for k, m in w.items():
    variants[k] = o[m]
# W5 employee: pre-work/lunch at touch+1min, others at 12:00 Paris market
ei1 = np.minimum(gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=1)), len(m1) - 1)
noon = S._local_times(pd.DatetimeIndex(tp.tz_localize(None).normalize()), "12:00", PARIS)
ei12 = np.minimum(gl.entry_index(m1, noon), len(m1) - 1)
a = ((hp >= 8) & (hp < 9)) | ((hp >= 12) & (hp < 13))
b = (hp >= 9) & (hp < 12)
variants["W5_employee(lunch-exec)"] = pd.concat([mk_market(a, ei1, dist), mk_market(b, ei12, dist)])
variants["W5b_only_09-12_at_noon"] = mk_market(b, ei12, dist)
# exits
xdates = pd.DatetimeIndex(o.date) + pd.offsets.BDay(int(PARAMS["hold_days"]))
x20 = gl.entry_index(m1, S._local_times(xdates, "20:00", PARIS))
xdates3 = pd.DatetimeIndex(o.date) + pd.offsets.BDay(int(PARAMS["hold_days"]) + 1)
x08 = gl.entry_index(m1, S._local_times(xdates3, "08:00", PARIS))
variants["E1_exit_20:00Paris"] = o.assign(exit_i=x20)
variants["E2_exit_next_08:00Paris"] = o.assign(exit_i=x08)
variants["E3_W1entries+exit20Paris"] = o[w["W1_wkday_08-20"]].assign(exit_i=x20[w["W1_wkday_08-20"]])
# combined realistic employee: W5 entries + exit next morning 08:00 Paris
e5 = variants["W5_employee(lunch-exec)"].copy()
dmap = pd.Series(x08, index=pd.DatetimeIndex(o.date))
e5["exit_i"] = dmap.reindex(pd.DatetimeIndex(e5.date)).to_numpy()
variants["E4_W5+exit_next_08:00"] = e5

frames = [t.assign(variant="baseline")]
for k, oo in variants.items():
    oo = oo[oo.exit_i > oo.entry_i].sort_values("entry_i")
    tt = gl.simulate(m1, oo, no_overlap=True)
    frames.append(tt.assign(variant=k))
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "availability windows W0-W5 + exit-time availability E1-E4")
rows = []
for k in ["baseline"] + list(variants):
    sa, sb = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, "IS_n": sa["n"], "IS_pf": sa["pf"], "IS_t": sa["t"], "IS_yrs": sa.get("yrs_pos"),
                 "IS_pfL": sa.get("pf_long"), "IS_pfS": sa.get("pf_short"),
                 "VAL_n": sb["n"], "VAL_pf": sb["pf"], "VAL_t": sb["t"], "VAL_pfL": sb.get("pf_long"),
                 "VAL_pfS": sb.get("pf_short")})
r = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(r.to_string(index=False))
r.to_csv(os.path.join(HERE, "p2_availability.csv"), index=False)
# per-hour PF of the baseline trades (no re-simulation): which hour carries the edge?
ht = t.entry_time.dt.tz_convert(PARIS).dt.hour
tib = is_part(t.assign(h=ht))
tvb = val_part(t.assign(h=ht), "baseline trades by Paris entry hour")
print("baseline trades by Paris entry hour  IS:", {h: (len(g), stats(g)["pf"]) for h, g in tib.groupby("h")})
print("                                   VAL:", {h: (len(g), stats(g)["pf"]) for h, g in tvb.groupby("h")})
