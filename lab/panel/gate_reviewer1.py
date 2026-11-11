import pandas as pd, numpy as np
S="/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/"
def ts(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    return x.mean()/x.std(ddof=1)*np.sqrt(len(x)) if len(x)>2 else np.nan
def pf(x): return x[x>0].sum()/-x[x<0].sum()
g=pd.read_csv(S+"dl/DIX.csv",parse_dates=['date']).set_index('date'); g=g[g.index<"2022-01-01"]
def pct(s,w=252): return s.rolling(w,min_periods=w//2).apply(lambda v:(v[:-1]<v[-1]).mean(),raw=True)
g['gex_prev']=g.gex.shift(1); g['gex_pct']=pct(g.gex_prev)
r=np.log(g.price).diff()
g['ret1']=r.shift(1)
g['rv5']=pct(r.rolling(5).std().shift(1)); g['rv20']=pct(r.rolling(20).std().shift(1))
g['absret1']=pct(r.abs().shift(1))
g['dd']=pct((g.price/g.price.rolling(20).max()-1).shift(1))   # low = deep drawdown
g['ret5']=pct(r.rolling(5).sum().shift(1))
try:
    v=pd.read_csv(S+"dl/vix.csv"); v["date"]=pd.to_datetime(v["DATE"],format="%m/%d/%Y"); v=v.set_index('date'); v=v[v.index<"2022-01-01"]
    vc=[c for c in v.columns if c.upper()=='CLOSE'][0]
    g['vix_prev']=v[vc].reindex(g.index).shift(1); g['vix']=pct(g.vix_prev)
except Exception as e: print("vix fail",e)
g['gex_lag60']=pct(g.gex.shift(61))
g['dix']=pct(g.dix.shift(1))
T=pd.read_csv("/home/user/gold-orb/lab/results/r2/idx_us/trades_is_noise30_us100.csv")
print(list(T.columns)); 
tc=[c for c in T.columns if 'entry' in c.lower() and 'time' in c.lower()][0]
T['t']=pd.to_datetime(T[tc],utc=True); T['d']=T.t.dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
T=T[T.d<"2022-01-01"].join(g,on='d')
E=T.dropna(subset=['gex_pct']).copy()
print("n",len(E),E.d.min(),E.d.max(), "sd R",E.R.std())
print("corr matrix pct vars (trade-level):"); print(E[['gex_pct','vix','rv5','rv20','absret1','dd','ret5','dix']].corr().round(2).iloc[0])
def split(col,lowside=True,thr=0.33):
    m=(E[col]<thr) if lowside else (E[col]>=1-thr)
    a=E.R[m]; b=E.R[~m]; d=a.mean()-b.mean(); se=np.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
    print(f" {col:10s} {'low' if lowside else 'high'} third: n={len(a):4d} expR={a.mean():+.3f} PF={pf(a):.2f} | rest n={len(b):4d} expR={b.mean():+.3f} PF={pf(b):.2f} | z={d/se:.2f}")
    return m
split('gex_pct'); split('vix',False); split('rv5',False); split('rv20',False); split('absret1',False); split('dd'); split('ret5'); split('gex_lag60'); split('dix'); split('dix',False)
# does gex add beyond vix?
if 'vix' in E:
    lg=E.gex_pct<0.33; hv=E.vix>=0.67
    for a,b,l in [(lg,hv,'lowGEX&highVIX'),(lg,~hv,'lowGEX&notHighVIX'),(~lg,hv,'notLowGEX&highVIX'),(~lg,~hv,'neither')]:
        x=E.R[a&b]; print(f"  {l:20s} n={len(x):4d} expR={x.mean():+.3f} t={ts(x):.2f}")
    lg=E.gex_pct<0.33; hv=E.dd<0.33
    for a,b,l in [(lg,hv,'lowGEX&deepDD'),(lg,~hv,'lowGEX&notDD'),(~lg,hv,'notLowGEX&deepDD'),(~lg,~hv,'neither')]:
        x=E.R[a&b]; print(f"  {l:20s} n={len(x):4d} expR={x.mean():+.3f} t={ts(x):.2f}")
# regression of R on pct vars
import numpy.linalg as la
for cols in (['gex_pct'],['vix'],['gex_pct','vix'],['gex_pct','dd'],['gex_pct','vix','dd','rv5']):
    X=E[cols].dropna(); y=E.R.loc[X.index]; A=np.c_[np.ones(len(X)),X.values]
    b=la.lstsq(A,y,rcond=None)[0]; res=y-A@b
    # day-clustered robust se
    grp=E.d.loc[X.index].values; M=np.zeros((A.shape[1],A.shape[1]))
    df=pd.DataFrame(A*res.values[:,None]); s=df.groupby(grp).sum().values; M=s.T@s
    V=la.inv(A.T@A)@M@la.inv(A.T@A); print(cols,"beta",np.round(b[1:],3),"t",np.round(b[1:]/np.sqrt(np.diag(V))[1:],2))
# by year
for y,x in E.groupby(E.d.dt.year):
    a=x.R[x.gex_pct<0.33]; b=x.R[x.gex_pct>=0.33]; print(y,len(a),round(a.mean(),3),len(b),round(b.mean(),3))
# drop best 5 days of low group
dd=E.groupby('d').agg(R=('R','sum'),p=('gex_pct','first'))
lo=dd[dd.p<0.33].R.sort_values(); print("low-gex days",len(lo),"sumR",lo.sum().round(1),"top10 days sum",lo.tail(10).sum().round(1),"top 10 dates",list(lo.tail(10).index.strftime('%Y-%m-%d')))
# 2020 share
print("2020 share of low sumR:", E.R[(E.gex_pct<0.33)&(E.d.dt.year==2020)].sum()/E.R[E.gex_pct<0.33].sum())
# permutation test for max over 9 variants: shuffle gex pct blocks by year? simple: circular shift of gex series
rng=np.random.default_rng(0); obs=E.R[E.gex_pct<0.33].mean()-E.R[E.gex_pct>=0.33].mean()
days=g.index[g.gex_pct.notna()]; cnt=0; N=2000; gp=g.gex_pct.dropna()
for i in range(N):
    k=rng.integers(40,len(gp)-40); sh=pd.Series(np.roll(gp.values,k),index=gp.index)
    p=E.d.map(sh); dlt=E.R[p<0.33].mean()-E.R[p>=0.33].mean(); cnt+= dlt>=obs
print("obs diff",round(obs,3),"circular-shift p (one-sided):",cnt/N)
