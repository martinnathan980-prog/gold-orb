"""P16: (a) swap share of the cost and PF sensitivity to the fixed 5%/2% swap assumption (multi-day holds);
(b) broker 'stops level': share of sessions where at 07:00 London the nearer level is within $0.30/$0.50 of the
current quote (a pending stop could be rejected -> EA must use virtual stops / market orders).  IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
from goldlab.sim import Costs
m1 = load()
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
oi = o[pd.to_datetime(o.date) < '2022-01-01'].reset_index(drop=True)
t = is_part(gl.simulate(m1, oi))
print("IS mean swap R/trade:", round((t.swap / t.risk).mean(), 4), " mean nights:", round((t.swap / (t.entry * np.where(t.side > 0, .05, .02) / 360)).mean(), 2),
      " commission R/trade:", round((t.commission / t.risk).mean(), 4))
for sl, ss in ((0.0, 0.0), (0.05, 0.02), (0.08, 0.0), (0.08, 0.03), (0.10, 0.05)):
    tt = is_part(gl.simulate(m1, oi, costs=Costs(swap_long=sl, swap_short=ss)))
    print(f"swap long {sl:.0%} short {ss:.0%}: {summ(tt)}")
# (b) stops level at arming time
PP = dict(S.DEFAULTS); PP.update(P)
s = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/sessions.pkl')
s = s[(s.width > 0) & (pd.to_datetime(s.date) < '2022-01-01')]
ao, bo = m1.ao.to_numpy(), m1.bo.to_numpy()
i1 = s.i1.to_numpy()
buy = s.hi + 0.1 * s.width; sell = s.lo - 0.1 * s.width
d = np.minimum(buy.to_numpy() - ao[i1], bo[i1] - sell.to_numpy())
for thr in (0.3, 0.5, 1.0):
    print(f"sessions where the nearer level is < ${thr} from the 07:00 quote: {(d < thr).mean():.3%}")
print("median distance to nearer level at 07:00: $", round(float(np.median(d)), 2), " median W $", round(float(s.width.median()), 2))
