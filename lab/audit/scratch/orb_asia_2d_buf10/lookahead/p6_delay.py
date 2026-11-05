"""P6: decision-time / fill-timing perturbations (does the result degrade smoothly or collapse?).
  A. alert mode: market entry at the OPEN of bar fi+k after the touch bar fi (k=1 is 'decide at the touch
     bar close, enter next bar'), same stop level and same time exit.  k = 1,2,3,5,10,15,30,60.
  B. pessimistic intrabar fill: stop entry filled at the worse of level and the touch bar's CLOSE.
  C. clock shifts of the decision: range end 06:59 / 07:01 / 07:05 (range and arming move together);
     arming delayed by +1/+5/+15 bars with the 00:00-07:00 range unchanged (touches before are ignored,
     and the day is NOT re-armed -> first touch after the delay).
All on IS; VAL through one logged cut per variant family."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index; N = len(m1)
ao, bo, ac, bc, ah, bl = (m1[c].to_numpy() for c in ('ao', 'bo', 'ac', 'bc', 'ah', 'bl'))
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
PP = dict(S.DEFAULTS); PP.update(P)
rows = []
VAL = {}
def run(nm, oo, extra=None):
    t = gl.simulate(m1, oo, no_overlap=True)
    VAL[nm] = t
    d = {"variant": nm, **{f"IS_{k}": v for k, v in summ(is_part(t)).items()}}
    if extra: d.update(extra)
    rows.append(d); print(d, flush=True)
    return t
run("base (stop entry @level, intrabar)", o)
# A. market entry k bars after the touch bar
for k in (1, 2, 3, 5, 10, 15, 30, 60):
    q = o.copy()
    q['entry_i'] = q.entry_i + k
    q = q[q.entry_i < q.exit_i].copy()
    q['etype'] = 0; q['level'] = np.nan; q['expiry_i'] = -1
    # how often is the stop already breached at the entry open?  (sim then exits at once: GAP)
    ei = q.entry_i.to_numpy()
    breached = np.where(q.side > 0, bo[ei] <= q.stop, ao[ei] >= q.stop).mean()
    # adverse/favourable move from level to entry price (in R of the planned risk)
    px = np.where(q.side > 0, ao[ei], bo[ei]); risk0 = (q.level_orig if 'level_orig' in q else o.loc[q.index, 'level'] - q.stop).abs()
    mv = (q.side * (px - o.loc[q.index, 'level'])) / (o.loc[q.index, 'level'] - q.stop).abs()
    run(f"A market @open fi+{k}", q, {"stop_breached_at_entry": round(float(breached), 4), "median_entry_move_R": round(float(mv.median()), 4), "mean_entry_move_R": round(float(mv.mean()), 4)})
# B. stop entry filled at the worse of level and the touch bar close -> emulate with a market order at the
#    close: use etype 1 with level := worse-of(level, close) on the same bar (still fills since ah>=level' ? not
#    guaranteed) -> do it as a market order on the NEXT bar's open is A1; here: shift the fill price explicitly.
t0 = gl.simulate(m1, o, no_overlap=True)
fi = o.loc[t0.index, 'entry_i'].to_numpy()
worse = np.where(t0.side > 0, np.maximum(o.loc[t0.index, 'level'], ac[fi]), np.minimum(o.loc[t0.index, 'level'], bc[fi]))
newentry = worse * (1 + 1.5e-4 * t0.side)
tb = t0.copy()
tb['entry'] = newentry
gross = tb.side * (tb.exit - tb.entry)
tb['pnl'] = gross - tb.swap - tb.commission
tb['risk'] = (tb.entry - tb.stop).abs(); tb['R'] = tb.pnl / tb.risk
VAL["B fill at worse(level, touch-bar close)"] = tb
d = {"variant": "B fill at worse(level, touch-bar close) [same trade set]", **{f"IS_{k}": v for k, v in summ(is_part(tb)).items()}}
rows.append(d); print(d, flush=True)
# C1. range end shifts (range + arming move together)
for re_ in ("06:59", "07:01", "07:05"):
    q = S.make_orders(m1, **{**P, "range_end": re_})
    run(f"C range_end {re_}", q)
# C2. arming delayed by j bars, range unchanged
s = S.sessions(m1, PP)
s = s[s.width > 0].reset_index(drop=True)
buf = 0.1 * s.width.to_numpy(); buy = s.hi.to_numpy() + buf; sell = s.lo.to_numpy() - buf
alw = np.ones(len(s), bool)
ahf, blf, aof, bof = (m1[c].to_numpy(np.float64) for c in ('ah', 'bl', 'ao', 'bo'))
for j in (1, 5, 15):
    i_start = np.minimum(s.i1.to_numpy(np.int64) + j, s.ie.to_numpy(np.int64))
    f, sd = S._first_touch(ahf, blf, aof, bof, i_start, s.ie.to_numpy(np.int64), buy, sell, alw, alw)
    ok = f >= 0
    q = pd.DataFrame({"entry_i": f[ok], "side": sd[ok], "etype": 1, "level": np.where(sd > 0, buy, sell)[ok], "expiry_i": f[ok],
                      "stop": np.where(sd > 0, sell, buy)[ok], "exit_i": s.ix.to_numpy(np.int64)[ok], "date": s.date.values[ok]})
    q = q[q.exit_i > q.entry_i].reset_index(drop=True)
    # trades whose first touch happened before the delayed arming are now entered on a later touch (or never)
    run(f"C arming delayed +{j} bars (range 00-07 unchanged)", q)
out = pd.DataFrame(rows)
out.to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p6_delay_is.csv', index=False)
# VAL: one logged access for the whole sweep
allv = pd.concat([t.assign(variant=k) for k, t in VAL.items()])
v = gl.cut(allv, "val", track="review", label=vlabel("decision-delay-sweep(A k=1..60, B close-fill, C range_end/arming shifts)"))
vr = pd.DataFrame([{"variant": k, **{f"VAL_{a}": b for a, b in summ(g).items()}} for k, g in v.groupby('variant', sort=False)])
vr.to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p6_delay_val.csv', index=False)
pd.set_option('display.width', 250)
print(out[['variant', 'IS_n', 'IS_pf', 'IS_t', 'IS_exp', 'IS_yrs+', 'IS_L_pf', 'IS_S_pf']].to_string())
print(vr[['variant', 'VAL_n', 'VAL_pf', 'VAL_t', 'VAL_exp', 'VAL_L_pf', 'VAL_S_pf']].to_string())
