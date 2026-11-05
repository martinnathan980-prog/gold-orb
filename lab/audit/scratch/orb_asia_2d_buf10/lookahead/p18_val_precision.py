"""P18: unrounded VAL PF on the patched data (criterion 7 is PF >= 1.10 on a value rounded to 3 decimals in
metrics.report), and the 2013-short concentration on the patched IS."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
from goldlab.evalkit import val_criteria
T = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')
v = val_part(T, "unrounded-VAL-PF-patched-data")
R = v.R.to_numpy()
print("VAL n", len(v), "unrounded PF %.6f" % pf(R), "| report() pf:", gl.report(v)["pf"], "| val_criteria:", val_criteria(gl.report(v)))
t = is_part(T)
s13 = t[(t.entry_time.dt.year == 2013) & (t.side < 0)].R.sum()
print("IS total R %.1f ; 2013 shorts R %.1f ; IS PF without 2013: %.3f" % (t.R.sum(), s13, pf(t[t.entry_time.dt.year != 2013].R)))
print("IS unrounded PF %.6f t %.4f" % (pf(t.R), tstat(t.R)))
