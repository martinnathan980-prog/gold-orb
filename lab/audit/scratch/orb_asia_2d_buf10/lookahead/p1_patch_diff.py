"""P1: what changed between unpatched data (report numbers) and patched data (current)? IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
D = 'audit/scratch/orb_asia_2d_buf10/lookahead/'
tp = is_part(pd.read_pickle(D + 'trades_base_full.pkl'))
tu = is_part(pd.read_pickle(D + 'trades_unpatched_full.pkl'))
op = pd.read_pickle(D + 'orders_base.pkl'); ou = pd.read_pickle(D + 'orders_unpatched.pkl')
op_is = op[pd.to_datetime(op.date) < '2022-01-01']; ou_is = ou[pd.to_datetime(ou.date) < '2022-01-01']
print("IS orders patched", len(op_is), "unpatched", len(ou_is))
dp, du = set(pd.to_datetime(op_is.date)), set(pd.to_datetime(ou_is.date))
print("order dates only in patched:", len(dp - du), " only in unpatched:", len(du - dp))
# compare orders on common dates
a = op_is.assign(date=pd.to_datetime(op_is.date)).set_index('date'); b = ou_is.assign(date=pd.to_datetime(ou_is.date)).set_index('date')
com = sorted(dp & du)
diff_side = (a.loc[com, 'side'] != b.loc[com, 'side']).sum()
diff_lv = (~np.isclose(a.loc[com, 'level'], b.loc[com, 'level'])).sum()
print("common order dates", len(com), "side differs", diff_side, "level differs", diff_lv)
tp['d'] = pd.to_datetime(tp.date); tu['d'] = pd.to_datetime(tu.date)
A = tp.set_index('d'); B = tu.set_index('d')
both = A.index.intersection(B.index)
onlyP = A.index.difference(B.index); onlyU = B.index.difference(A.index)
print("trades: both", len(both), "only patched", len(onlyP), "only unpatched", len(onlyU))
dR = (A.loc[both, 'R'] - B.loc[both, 'R'])
chg = dR[dR.abs() > 1e-6]
print("common trades with different R:", len(chg), "sum dR (patched-unpatched)", round(chg.sum(), 2))
print(pd.DataFrame({'R_unp': B.loc[chg.index, 'R'].round(2), 'R_pat': A.loc[chg.index, 'R'].round(2),
                    'rs_unp': B.loc[chg.index, 'reason'], 'rs_pat': A.loc[chg.index, 'reason'],
                    'x_unp': B.loc[chg.index, 'exit_time'], 'x_pat': A.loc[chg.index, 'exit_time']}).to_string())
print("only-patched trades R sum", round(A.loc[onlyP, 'R'].sum(), 2), "n", len(onlyP))
print("only-unpatched trades R sum", round(B.loc[onlyU, 'R'].sum(), 2), "n", len(onlyU))
print("PF of only-patched", round(pf(A.loc[onlyP, 'R']), 3), "PF only-unpatched", round(pf(B.loc[onlyU, 'R']), 3))
