"""Data facts relevant to look-ahead / fidelity: coverage, holes, bar labelling (start vs end), FP frame vs raw."""
from common import *

res = {}
# ---------------------------------------------------------------- BTC (follower) FP frame
m1 = r2.load("btcusd")
idx = m1.index
print("BTC FP frame", len(m1), idx[0], idx[-1], "tz", idx.tz, "unit", idx.unit)
tm = (idx.asi8 // (60 * 10 ** 9 if idx.unit == "ns" else 60 * 10 ** {"us": 6, "ms": 3, "s": 0}[idx.unit])).astype(np.int64)
assert (np.diff(tm) > 0).all(), "index not strictly increasing"
assert ((idx.asi8 % (60 * 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[idx.unit])) == 0).all(), "bars not on minute boundaries"
gaps = np.diff(tm)
yr = idx.year.to_numpy()
by = {}
ny = idx.tz_convert("America/New_York")
nym = (ny.hour * 60 + ny.minute).to_numpy()
wd = ny.dayofweek.to_numpy()
cash = (nym >= 570) & (nym < 1020) & (wd < 5)        # 09:30-17:00 NY (decision + holding window)
for y in range(2017, 2026):
    k = yr == y
    kc = k & cash
    days = np.unique(ny[kc].normalize()).size
    by[y] = {"bars": int(k.sum()), "bars_per_cash_window_day(450 possible)": round(float(kc.sum() / max(days, 1)), 1),
             "weekday_days_with_cash_bars": int(days),
             "gaps>=5min": int((gaps[k[1:]] >= 5).sum()), "gaps>=30min": int((gaps[k[1:]] >= 30).sum()),
             "max_gap_min": int(gaps[k[1:]].max()),
             "weekend_bars": int((k & (idx.dayofweek.to_numpy() >= 5)).sum()),
             "median_spread_bp": round(float(((m1.ac - m1.bc) / ((m1.ac + m1.bc) / 2) * 1e4)[k].median()), 3)}
    print(y, by[y], flush=True)
res["btc_fp_by_year"] = by
# gaps inside the weekday cash window (09:30-17:00 NY): where and how long
g_i = np.flatnonzero(gaps >= 3)
gin = [(str(idx[i]), int(gaps[i])) for i in g_i if cash[i] and yr[i] <= 2021]
print("IS: BTC gaps >= 3 min starting inside the weekday 09:30-17:00 NY window:", len(gin))
gl_ = pd.Series([g for _, g in gin])
print(gl_.describe().to_dict() if len(gl_) else None)
res["btc_is_gaps_ge3_in_cash_window"] = {"n": len(gin), "by_len": gl_.value_counts().sort_index().to_dict() if len(gl_) else {}}
# time-of-day structure of the BTC gaps >= 30 min (any day, IS)
big = [(str(idx[i]), str(idx[i + 1]), int(gaps[i])) for i in np.flatnonzero(gaps >= 30) if yr[i] <= 2021]
print("IS BTC gaps >= 30 min:", len(big))
for b in big[:15] + big[-15:]:
    print("   ", b)
hh = pd.Series([pd.Timestamp(b[0]).tz_convert("America/New_York").strftime("%a %H") for b in big]).value_counts().head(12)
print("gap start (NY weekday hour) top:", hh.to_dict())
res["btc_is_big_gaps"] = {"n": len(big), "start_ny_top": hh.to_dict()}
btc_mid_c = ((m1.bc + m1.ac) / 2)
# flat-ish bars and zero-range share
res["btc_zero_range_share"] = float(((m1.bh == m1.bl)).mean())
print("BTC zero-range bars share:", res["btc_zero_range_share"])
del m1
r2.free(); gc.collect()

# ---------------------------------------------------------------- US100 (leader) FP frame
L = r2.load("us100")
li = L.index
print("US100 FP frame", len(L), li[0], li[-1])
ltm = (li.asi8 // (60 * 10 ** {"ns": 9, "us": 6, "ms": 3, "s": 0}[li.unit])).astype(np.int64)
lg = np.diff(ltm)
lny = li.tz_convert("America/New_York")
lnym = (lny.hour * 60 + lny.minute).to_numpy()
lwd = lny.dayofweek.to_numpy()
lyr = li.year.to_numpy()
sess = (lnym >= 570) & (lnym < 960) & (lwd < 5)
byl = {}
for y in range(2017, 2026):
    k = (lyr == y) & sess
    days = np.unique(lny[k].normalize()).size
    # holes inside the session: bar in session whose previous bar is not the previous minute
    prev_gap = np.r_[1, lg]
    hole = k & (prev_gap > 1) & (lnym > 570)
    byl[y] = {"session_days": int(days), "bars_per_session_day(390 possible)": round(float(k.sum() / max(days, 1)), 2),
              "session_bars_after_hole": int(hole.sum()), "after_hole_2to4min": int((hole & (prev_gap <= 4)).sum()),
              "after_hole_gt4min": int((hole & (prev_gap > 4)).sum())}
    print(y, byl[y], flush=True)
res["us100_by_year"] = byl
# is the 09:29 bar present before the 09:30 bar? (the first decision bar's return spans the cash open)
k930 = (lnym == 570) & (lwd < 5) & (lyr >= 2017)
prev_gap = np.r_[1, lg]
print("09:30 bars:", int(k930.sum()), "| with the 09:29 bar present:", int((k930 & (prev_gap == 1)).sum()))

# ---------------------------------------------------------------- bar labelling: START or END?
# Scheduled events hit at second 0 of a NY minute: 08:30 (macro releases), 09:30 (cash open), 10:00 (ISM etc.), 14:00 (FOMC days).
# If bars are START-labelled the jump is in the bar labelled hh:mm; if END-labelled it would be in the bar labelled hh:mm+1.
lmid = ((L.bc + L.ac) / 2).to_numpy()
lopen = ((L.bo + L.ao) / 2).to_numpy()
rng_bp = (((L.bh + L.ah) / 2 - (L.bl + L.al) / 2) / lmid * 1e4).to_numpy()
is_k = (lyr >= 2017) & (lyr <= 2021) & (lwd < 5)
lab = {}
for name, mm in (("08:30", 510), ("09:30", 570), ("10:00", 600), ("14:00", 840)):
    row = {}
    for off in (-2, -1, 0, 1, 2):
        k = is_k & (lnym == mm + off)
        row[f"{off:+d}"] = round(float(np.mean(rng_bp[k])), 2)
    lab[name] = row
    print("US100 mean M1 range (bp) around", name, "NY (IS 2017-21):", row)
res["us100_range_around_events_bp"] = lab
# gap between the previous bar's close and this bar's open (should be ~0 inside continuous trading: a jump that sits
# BETWEEN bars would point to mislabelled / shifted bars)
oc = np.abs(np.log(lopen[1:] / lmid[:-1])) * 1e4
kk = is_k[1:] & (lg == 1)
for name, mm in (("08:30", 510), ("09:30", 570), ("14:00", 840)):
    k = kk & (lnym[1:] == mm)
    print(f"US100 |open(t) - close(t-1)| at {name}: mean {oc[k].mean():.2f} bp vs bar range {rng_bp[1:][k].mean():.2f} bp")
del L
r2.free(); gc.collect()

# BTC around the same instants (2020-2021, when it reacts to macro news)
m1 = r2.load("btcusd", end="2022-01-01")
bi = m1.index
bny = bi.tz_convert("America/New_York")
bnym = (bny.hour * 60 + bny.minute).to_numpy()
bwd = bny.dayofweek.to_numpy()
byr = bi.year.to_numpy()
bm = ((m1.bc + m1.ac) / 2).to_numpy()
brng = (((m1.bh + m1.ah) / 2 - (m1.bl + m1.al) / 2) / bm * 1e4).to_numpy()
labb = {}
for name, mm in (("08:30", 510), ("09:30", 570), ("10:00", 600), ("14:00", 840)):
    row = {}
    for off in (-2, -1, 0, 1, 2):
        k = (byr >= 2020) & (bwd < 5) & (bnym == mm + off)
        row[f"{off:+d}"] = round(float(np.mean(brng[k])), 2)
    labb[name] = row
    print("BTC mean M1 range (bp) around", name, "NY (2020-21):", row)
res["btc_range_around_events_bp"] = labb
dump(res, "a01_data.json")
