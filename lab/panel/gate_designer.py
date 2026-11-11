import pandas as pd, numpy as np
def tstat(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    return x.mean()/x.std(ddof=1)*np.sqrt(len(x)) if len(x)>2 else np.nan
g=pd.read_csv("../dl/DIX.csv",parse_dates=['date']).set_index('date')
g=g[g.index<"2022-01-01"]
g['gex_prev']=g.gex.shift(1)
g['gex_pct']=g.gex_prev.rolling(252,min_periods=120).apply(lambda w:(w[:-1]<w[-1]).mean(),raw=True)
# trailing realised vol proxy from SPX daily closes (known before the open)
r=np.log(g.price).diff()
g['rv20']=r.rolling(20).std().shift(1)
g['rv_pct']=g.rv20.rolling(252,min_periods=120).apply(lambda w:(w[:-1]<w[-1]).mean(),raw=True)
print("corr gex_pct, rv_pct:",g[['gex_pct','rv_pct']].corr().iloc[0,1])
for name in ['noise30','ocm4']:
    T=pd.read_csv(f"/home/user/gold-orb/lab/results/r2/idx_us/trades_is_{name}_us100.csv")
    tc=[c for c in T.columns if 'time' in c.lower() or c.lower() in('t_entry','entry_t','entry')]
    rc=[c for c in T.columns if c.lower() in('r','r_mult','pnl_r','R')]
    print(name,list(T.columns))
    T['t']=pd.to_datetime(T[tc[0]],utc=True)
    T['d']=T.t.dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
    T=T[T.d<"2022-01-01"]
    T=T.join(g[['gex_prev','gex_pct','rv_pct']],on='d')
    R=T[rc[0]]
    print(f" all n={len(T)} expR={R.mean():.3f} t={tstat(R):.2f} PF={R[R>0].sum()/-R[R<0].sum():.2f}")
    E=T.dropna(subset=['gex_pct'])
    for lbl,col in [('gex_pct','gex_pct'),('rv_pct','rv_pct')]:
        for lo,hi in [(0,0.2),(0.2,0.5),(0.5,0.8),(0.8,1.01),(0,0.33),(0.33,1.01),(0,0.5),(0.5,1.01)]:
            m=(E[col]>=lo)&(E[col]<hi); x=E[rc[0]][m]
            print(f"  {lbl} [{lo},{hi}) n={m.sum():4d} expR={x.mean():+.3f} t={tstat(x):5.2f} PF={x[x>0].sum()/-x[x<0].sum():.2f} win={np.mean(x>0):.3f} sumR={x.sum():.1f}")
    # two-way: low gex within low/high rv
    for a,b,lbl in [(E.gex_pct<0.33,E.rv_pct>=0.67,'lowGEX & highRV'),(E.gex_pct<0.33,E.rv_pct<0.67,'lowGEX & not highRV'),(E.gex_pct>=0.33,E.rv_pct>=0.67,'not lowGEX & highRV'),(E.gex_pct>=0.33,E.rv_pct<0.67,'neither')]:
        x=E[rc[0]][a&b]; print(f"  {lbl:22s} n={len(x):4d} expR={x.mean():+.3f} t={tstat(x):5.2f}")
    # by sub-period for low gex tercile
    for a,b in [('2013','2016'),('2017','2019'),('2020','2021')]:
        mm=(E.d>=a)&(E.d<str(int(b)+1))
        x1=E[rc[0]][mm&(E.gex_pct<0.33)]; x2=E[rc[0]][mm&(E.gex_pct>=0.33)]
        print(f"  {a}-{b}: lowGEX n={len(x1)} expR={x1.mean():+.3f} | rest n={len(x2)} expR={x2.mean():+.3f}")
