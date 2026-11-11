import pandas as pd, numpy as np
S="/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/"
def ts(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    return x.mean()/x.std(ddof=1)*np.sqrt(len(x)) if len(x)>2 else np.nan
def pf(x): return x[x>0].sum()/-x[x<0].sum()
g=pd.read_csv(S+"dl/DIX.csv",parse_dates=['date']).set_index('date'); g=g[g.index<"2022-01-01"]
def pct(s,w=252): return s.rolling(w,min_periods=w//2).apply(lambda v:(v[:-1]<v[-1]).mean(),raw=True)
g['gex_pct']=pct(g.gex.shift(1))
r=np.log(g.price).diff()
for k in (1,2,3,5,10,20): g[f'ret{k}']=pct(r.rolling(k).sum().shift(1))
T=pd.read_csv("/home/user/gold-orb/lab/results/r2/idx_us/trades_is_noise30_us100.csv")
T['t']=pd.to_datetime(T['entry_time'],utc=True); T['d']=T.t.dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
E=T[T.d<"2022-01-01"].join(g,on='d').dropna(subset=['gex_pct','ret20']).copy()
for k in (1,2,3,5,10,20):
    m=E[f'ret{k}']<0.33; a=E.R[m]; b=E.R[~m]; se=np.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
    print(f"ret{k} low third n={len(a)} {a.mean():+.3f} PF {pf(a):.2f} | rest {b.mean():+.3f} PF {pf(b):.2f} z={(a.mean()-b.mean())/se:.2f}  corr with gex_pct {E[f'ret{k}'].corr(E.gex_pct):.2f}")
lg=E.gex_pct<0.33; lr=E.ret5<0.33
for a,b,l in [(lg,lr,'lowGEX & lowRet5'),(lg,~lr,'lowGEX & notLowRet5'),(~lg,lr,'notLowGEX & lowRet5'),(~lg,~lr,'neither')]:
    x=E.R[a&b]; print(f"  {l:22s} n={len(x):4d} expR={x.mean():+.3f} t={ts(x):.2f}")
# side split: long vs short trades in low gex
for s,x in E.groupby('side'):
    a=x.R[x.gex_pct<0.33]; b=x.R[x.gex_pct>=0.33]; print("side",s,len(a),round(a.mean(),3),len(b),round(b.mean(),3))
# sizing: 2x/0.5x vs flat: daily Sharpe
for lo,hi in ((1,1),(2,0.5),(1.5,0.75)):
    w=np.where(lg,lo,hi); x=E.R*w; d=x.groupby(E.d).sum()
    print(f"weights {lo}/{hi}: avg w {w.mean():.2f} sumR {x.sum():.1f} daily t {ts(d):.2f} sharpe-ish {d.mean()/d.std():.4f} worst day {d.min():.1f} maxDD {(d.cumsum()-d.cumsum().cummax()).min():.1f}")
# what if no effect: both groups at pooled mean -> sharpe change from weights
mu=E.R.mean(); sd=E.R.std(); p=lg.mean()
for lo,hi in ((2,0.5),(1.5,0.75)):
    m=(p*lo+(1-p)*hi)*mu; v=np.sqrt(p*lo**2+(1-p)*hi**2)*sd
    print(f"null: weights {lo}/{hi} sharpe ratio vs flat = {(m/v)/(mu/sd):.3f}  (avg weight {(p*lo+(1-p)*hi):.2f})")
# stop_bp by regime (is bp gap just bigger stops?)
print(E.groupby(lg)[['stop_bp','bp','R']].mean().round(3))
# validation power: sd R by group
print("sd R low",E.R[lg].std().round(3),"rest",E.R[~lg].std().round(3))
