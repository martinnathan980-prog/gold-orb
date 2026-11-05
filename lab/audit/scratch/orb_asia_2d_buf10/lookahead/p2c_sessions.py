import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load()
PP = dict(S.DEFAULTS); PP.update(P)
s = S.sessions(m1, PP)
s['rs_utc'] = s.t_rs.dt.strftime('%H:%M'); s['re_utc'] = s.t_re.dt.strftime('%H:%M'); s['x_utc'] = pd.DatetimeIndex(s.t_x).strftime('%H:%M')
s['month'] = s.date.dt.month
print("range start UTC by month:\n", s.groupby('month').rs_utc.agg(lambda x: x.value_counts().to_dict()).to_string())
print("exit 16:00 NY in UTC by month:\n", s.groupby('month').x_utc.agg(lambda x: x.value_counts().to_dict()).to_string())
for d in ("2019-03-11", "2019-03-29", "2019-04-01", "2019-10-28", "2019-11-01", "2019-11-04"):
    r = s[s.date == d]
    if len(r):
        r = r.iloc[0]
        print(d, "range", r.t_rs, "->", r.t_re, "entry until", r.t_ee, "exit", r.t_x)
# nbars distribution in range: holes in the range
print("range nbars (expected 420):", s.nbars.describe().round(1).to_dict())
print("sessions with nbars<400:", int((s.nbars < 400).sum()), " <380:", int((s.nbars < 380).sum()), " <300:", int((s.nbars < 300).sum()), "of", len(s))
# entry-window bars (expected 300)
s['nent'] = s.ie - s.i1
print("entry-window bars (expected 300):", s.nent.describe().round(1).to_dict(), " <280:", int((s.nent < 280).sum()))
s.to_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/sessions.pkl')
