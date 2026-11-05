"""P11: the live frictions re-run under the Amendment-1 'low_cost_ecn' scenario (the only broker setting
in which a CONDITIONAL candidate is meant to be traded).  Scenario-consistent: the quote frame is
spread-scaled (x0.35 around mid) BEFORE make_orders (range = max Ask / min Bid, first touches are
pre-resolved from quotes), then simulated with spread_mult=1.  Own transform (no new goldlab helpers).
"""
import gc
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

SC = json.load(open(os.path.join(LAB, "audit", "cost_scenarios.json")))["low_cost_ecn"]
LC = Costs(commission=SC["commission"], slip_bps=SC["slip_bps"], swap_long=SC["swap_long"],
           swap_short=SC["swap_short"], spread_mult=1.0)
K = SC["spread_mult"]


def scale(m, k, mask=None):
    sp = (m["ac"] - m["bc"]).to_numpy()
    h = sp * (k - 1) / 2 if mask is None else np.where(mask, sp * (k - 1) / 2, 0.0)
    out = m.copy()
    for c in ("bo", "bh", "bl", "bc"):
        out[c] = m[c].to_numpy() - h
    for c in ("ao", "ah", "al", "ac"):
        out[c] = m[c].to_numpy() + h
    return out


m0 = gl.load_m1("xauusd")
m1 = scale(m0, K)
idx = m1.index
ao, bo = m1.ao.to_numpy(), m1.bo.to_numpy()
frames = []


def sim(m, o, tag, costs=LC, no_overlap=True):
    tt = gl.simulate(m, o, costs=costs, no_overlap=no_overlap)
    frames.append(tt.assign(variant=tag))
    return tt


o = S.make_orders(m1, **PARAMS).reset_index(drop=True)
t = sim(m1, o, "LC_baseline")
# LC cost stress x1.5 (commission, slippage, spread multiplier), scenario-consistent
m_st = scale(m0, K * 1.5)
sim(m_st, S.make_orders(m_st, **PARAMS), "LC_stress_x1.5",
    costs=Costs(commission=LC.commission * 1.5, slip_bps=LC.slip_bps * 1.5, swap_long=LC.swap_long, swap_short=LC.swap_short))
del m_st
gc.collect()
# ---- manual delay
fi = o.entry_i.to_numpy()
dist = (o.level - o.stop).abs().to_numpy()


def delayed(o, N, conv):
    fi = o.entry_i.to_numpy()
    ei = np.minimum(gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=N)), len(m1) - 1)
    oo = pd.DataFrame({"entry_i": ei, "side": o.side.to_numpy(), "etype": 0, "exit_i": o.exit_i.to_numpy(), "date": o.date.to_numpy()})
    if conv == "dist":
        oo["stop"], oo["stop_dist"] = np.nan, (o.level - o.stop).abs().to_numpy()
    else:
        oo["stop"] = o.stop.to_numpy()
        q = np.where(oo.side > 0, bo[ei], ao[ei])
        oo = oo[~np.where(oo.side > 0, q <= oo.stop, q >= oo.stop)]
    return oo[oo.exit_i > oo.entry_i]


for N in (1, 5, 15, 60, 240):
    for conv in ("dist", "abs"):
        sim(m1, delayed(o, N, conv), f"LC_delay_N{N}_{conv}")
for N in range(1, 16):
    sim(m1, delayed(o, N, "dist"), f"LCsweep_N{N}_dist")
    sim(m1, delayed(o, N, "abs"), f"LCsweep_N{N}_abs")
# ---- availability
tp = idx[fi].tz_convert(PARIS)
hp = np.asarray(tp.hour + tp.minute / 60)
pre, lun, mid = (hp >= 8) & (hp < 9), (hp >= 12) & (hp < 13), (hp >= 9) & (hp < 12)
sim(m1, o[pre], "LC_W2_prework_08-09")
sim(m1, o[pre | lun], "LC_W4_pre+lunch")
ei1 = np.minimum(gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=1)), len(m1) - 1)
noon = S._local_times(pd.DatetimeIndex(tp.tz_localize(None).normalize()), "12:00", PARIS)
ei12 = np.minimum(gl.entry_index(m1, noon), len(m1) - 1)
xd2 = pd.DatetimeIndex(o.date) + pd.offsets.BDay(2)
xd3 = pd.DatetimeIndex(o.date) + pd.offsets.BDay(3)
x20 = gl.entry_index(m1, S._local_times(xd2, "20:00", PARIS))
x08 = gl.entry_index(m1, S._local_times(xd3, "08:00", PARIS))
sel = pre | lun | mid
w5 = pd.DataFrame({"entry_i": np.where(pre | lun, ei1, ei12)[sel], "side": o.side.to_numpy()[sel], "etype": 0, "stop": np.nan,
                   "stop_dist": dist[sel], "exit_i": o.exit_i.to_numpy()[sel], "date": o.date.to_numpy()[sel]}).sort_values("entry_i")
sim(m1, w5, "LC_W5_employee_lunch_exec")
sim(m1, w5.assign(exit_i=x08[sel][np.argsort(np.where(pre | lun, ei1, ei12)[sel], kind="stable")]), "LC_E4_W5+exit_next_08Paris")
sim(m1, o.assign(exit_i=x20), "LC_E1_exit_20Paris")
sim(m1, o.assign(exit_i=x08), "LC_E2_exit_next_08Paris")
# ---- clock mapping
S.TZ["UTC"] = "UTC"
for tag, over in {"LC_C1_NYclose_fixed_hours": dict(tz="NY", range_start="-05:00", range_end="02:00", entry_end="07:00"),
                  "LC_C2_EET_fixed_hours": dict(exit_tz="LDN", exit_time="21:00"),
                  "LC_C3_fixed_UTC": dict(tz="UTC", range_start="00:00", range_end="07:00", entry_end="12:00", exit_tz="UTC", exit_time="21:00"),
                  "LC_C4_winter_hours_range": dict(tz="UTC", range_start="00:00", range_end="07:00", entry_end="12:00")}.items():
    sim(m1, S.make_orders(m1, **{**PARAMS, **over}), tag)
# ---- rollover: x2 in 16-17 & 18-19 NY; ECN reopen x10 at 18:00-18:05 NY (COSTS.md: x8-11 at an ECN)
ny = idx.tz_convert(gl.NY)
mm = np.asarray(ny.hour * 60 + ny.minute)
W2 = ((mm >= 960) & (mm < 1020)) | ((mm >= 1080) & (mm < 1140))
RO = (mm >= 1080) & (mm < 1085)
mr = scale(m1, 2.0, W2)
sim(mr, S.make_orders(mr, **PARAMS), "LC_rollover_x2_2h")
del mr
gc.collect()
mr = scale(m1, 10.0, RO)
sim(mr, S.make_orders(mr, **PARAMS), "LC_reopen_18:00-18:05_x10")
mrr = scale(mr, 2.0, W2 & ~RO)
del mr
gc.collect()
# ---- position policy
ind = gl.simulate(m1, o, costs=LC, no_overlap=False)
frames.append(ind.assign(variant="LC_V3_every_signal"))
o4 = o.sort_values("entry_i").copy()
o4["exit_i"] = np.minimum(o4.exit_i.to_numpy(), np.r_[o4.entry_i.to_numpy()[1:], np.iinfo(np.int64).max])
sim(m1, o4[o4.exit_i > o4.entry_i], "LC_V4_newest_wins", no_overlap=False)
# ---- feed noise + combined (EA: noise 0.5bp + rollover x2 + reopen x10), 20 seeds
s, p = finalist_sessions(m1)
H, L = s.hi.to_numpy(), s.lo.to_numpy()
px = 0.5 * (H + L)
rng = np.random.default_rng(5)
for k in range(20):
    e1, e2 = rng.normal(0, 0.5e-4, len(s)) * px, rng.normal(0, 0.5e-4, len(s)) * px
    hh, ll = H + e1, L + e2
    w = hh - ll
    on = orders_from_levels(m1, s, hh + 0.1 * w, ll - 0.1 * w)
    sim(m1, on, f"LCnoise_s{k}")
    sim(mrr, on, f"LCcombEA_s{k}")
    sim(mrr, delayed(on, 5, "abs"), f"LCcombM5abs_s{k}")
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "low_cost_ecn scenario: delays, availability, clocks, rollover/reopen, policy, feed noise, combos")
rows = []
for k in allt.variant.unique():
    a, b = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, "IS_n": a["n"], "IS_pf": a["pf"], "IS_t": a["t"], "IS_yrs": a["yrs_pos"],
                 "VAL_n": b["n"], "VAL_pf": b["pf"], "VAL_t": b["t"]})
r = pd.DataFrame(rows)
r.to_csv(os.path.join(HERE, "p11_lowcost.csv"), index=False)
pd.set_option("display.width", 250)
print(r[~r.variant.str.startswith(("LCnoise", "LCcomb", "LCsweep"))].to_string(index=False))
for pre_ in ("LCsweep_N", ):
    for conv in ("dist", "abs"):
        q = r[r.variant.str.startswith(pre_) & r.variant.str.endswith(conv)]
        print(f"LC delay sweep N=1..15 {conv}: IS PF min/med/max {q.IS_pf.min():.3f}/{q.IS_pf.median():.3f}/{q.IS_pf.max():.3f} "
              f"share IS>=1.20 & t>=2: {np.mean((q.IS_pf >= 1.2) & (q.IS_t >= 2)):.2f} | VAL PF min/med/max {q.VAL_pf.min():.3f}/"
              f"{q.VAL_pf.median():.3f}/{q.VAL_pf.max():.3f} share VAL>=1.10: {np.mean(q.VAL_pf >= 1.1):.2f}")
for pre_ in ("LCnoise_s", "LCcombEA_s", "LCcombM5abs_s"):
    q = r[r.variant.str.startswith(pre_)]
    print(f"{pre_[:-2]} (20 seeds): IS PF p5/p50/p95 {np.percentile(q.IS_pf, 5):.3f}/{np.median(q.IS_pf):.3f}/{np.percentile(q.IS_pf, 95):.3f} "
          f"share IS>=1.20&t>=2 {np.mean((q.IS_pf >= 1.2) & (q.IS_t >= 2)):.2f} | VAL PF p5/p50/p95 {np.percentile(q.VAL_pf, 5):.3f}/"
          f"{np.median(q.VAL_pf):.3f}/{np.percentile(q.VAL_pf, 95):.3f} share VAL>=1.10 {np.mean(q.VAL_pf >= 1.1):.2f}")
tl = t
print("LC baseline cost per trade $/oz: swap+comm", round(float((tl.swap + tl.commission).mean()), 3))
