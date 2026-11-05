"""P6b: is the fi+60 collapse an R-normalisation artefact (entry next to the stop -> tiny risk)?
Re-score the delayed market entries (IS only) with R measured on the PLANNED risk |level - stop| and with a
'no-entry if remaining risk < 50% of planned' rule."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); ao, bo = m1.ao.to_numpy(), m1.bo.to_numpy()
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
o['planned'] = (o.level - o.stop).abs()
rows = []
for k in (0, 1, 2, 5, 15, 30, 60, 120):
    q = o.copy()
    if k:
        q['entry_i'] = q.entry_i + k; q = q[q.entry_i < q.exit_i].copy(); q['etype'] = 0; q['level'] = np.nan; q['expiry_i'] = -1
    for rule in ("all", "skip if remaining risk < 50% planned"):
        qq = q
        if rule != "all" and k:
            ei = qq.entry_i.to_numpy(); px = np.where(qq.side > 0, ao[ei], bo[ei])
            rem = qq.side * (px - qq.stop)
            qq = qq[rem >= 0.5 * qq.planned]
        qq = qq.reset_index(drop=True)
        t = is_part(gl.simulate(m1, qq, no_overlap=True))
        Rp = t.pnl / qq.loc[t.index, 'planned']
        rows.append({"k": k, "rule": rule, "n": len(t), "PF_R(actual risk)": round(pf(t.R), 3), "min_R": round(t.R.min(), 1),
                     "PF_R(planned risk)": round(pf(Rp), 3), "t(planned)": round(tstat(Rp), 2), "exp(planned)": round(Rp.mean(), 4),
                     "PF_$": round(pf(t.pnl), 3)})
        if rule == "all" and k == 60:
            w = t.nsmallest(3, 'R')[['entry_time', 'side', 'entry', 'stop', 'exit', 'reason', 'R']]
            print("worst R at k=60:\n", w.to_string())
out = pd.DataFrame(rows); print(out.to_string())
out.to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p6b_delay_outliers.csv', index=False)
