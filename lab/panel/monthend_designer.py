import sys; sys.dont_write_bytecode=True
sys.path.insert(0, "/home/user/gold-orb/lab")
import pandas as pd, numpy as np
import goldlab as gl
from goldlab import r2
bp=1e4
def ts(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    return x.mean()/x.std(ddof=1)*np.sqrt(len(x)) if len(x)>2 else np.nan
g=pd.read_csv("../dl/DIX.csv",parse_dates=['date']).set_index('date'); g=g[g.index<"2022-01-01"]
px=g.price
pme=px.groupby(px.index.to_period('M')).last().shift(1)
pm=pd.Series(px.index.to_period('M').map(pme).values,index=px.index)
mtd_prev=(px.shift(1)/pm-1)
usd_dir={'eurusd':-1,'gbpusd':-1,'audusd':-1,'nzdusd':-1,'usdjpy':1,'usdcad':1,'usdchf':1}
rows=[]
for sym in usd_dir:
    m1=r2.load(sym, end="2022-01-01")
    ld=pd.DatetimeIndex(gl.local(m1.index, gl.LDN)).tz_localize(None)
    hm=ld.hour*60+ld.minute
    k=(hm>=14*60)&(hm<=18*60+5)
    df=pd.DataFrame({'bo':m1.bo.values[k],'ao':m1.ao.values[k],'bc':m1.bc.values[k],'ac':m1.ac.values[k],'d':ld.normalize()[k],'hm':hm[k]})
    def col(T,c):
        x=df[df.hm==T].set_index('d')[c]; return x[~x.index.duplicated()]
    D=pd.DataFrame(index=sorted(df.d.unique()))
    for T in (900,945,955,960,962,965,970,975,990,1020,1080):
        D[f'b{T}']=col(T,'bo'); D[f'a{T}']=col(T,'ao')   # open of the bar starting at T
    D=D.dropna(); D=D[D.index.dayofweek<5]
    per=D.index.to_period('M'); last=pd.Series(D.index,index=D.index).groupby(per).transform('max')
    # rank from the end of the month: 0 = last weekday with data
    D['rk']=pd.Series(D.index,index=D.index).groupby(per).rank(ascending=False).values-1
    D['mtd']=mtd_prev.reindex(D.index); D['sym']=sym; D['u']=usd_dir[sym]
    rows.append(D); r2.free()
A=pd.concat(rows).dropna(subset=['mtd'])
A['q']=A.index.month.isin([3,6,9,12])
def trade(X,dirn,Te,Tx):
    """dirn: +1 buy USD, -1 sell USD (Series). returns (net, gross) fractional returns in pair terms"""
    pos=dirn*X.u            # +1 long pair
    me=(X[f'b{Te}']+X[f'a{Te}'])/2; mx=(X[f'b{Tx}']+X[f'a{Tx}'])/2
    gross=pos*(mx/me-1)
    ent=np.where(pos>0,X[f'a{Te}'],X[f'b{Te}']); ext=np.where(pos>0,X[f'b{Tx}'],X[f'a{Tx}'])
    net=pos*(ext/ent-1)
    return pd.Series(net,index=X.index), gross
def rep(lbl,X,dirn,Te,Tx):
    n,gr=trade(X,dirn,Te,Tx)
    dn=n.groupby(level=0).mean(); dg=gr.groupby(level=0).mean()
    print(f"  {lbl:44s} trades={len(n):4d} dates={len(dn):3d} gross={dg.mean()*bp:6.2f}bp net={dn.mean()*bp:6.2f}bp t_net(dates)={ts(dn):5.2f} win_dates={np.mean(dn>0):.3f}")
    return dn
ME=A[A.rk==0]
print("MONTH-END (last weekday), 7 USD pairs, FP bid/ask. Frequency of SPX MTD>0:",round((ME.groupby(level=0).mtd.first()>0).mean(),3))
one=pd.Series(1.0,index=ME.index)
print(" A. signed by SPX month-to-date (buy USD after the fix if SPX is up on the month)")
for Te,Tx in [(960,990),(962,990),(965,990),(970,990),(960,975),(960,1020),(965,1020),(965,1080),(990,1080)]:
    rep(f"entry {Te//60}:{Te%60:02d} exit {Tx//60}:{Tx%60:02d}",ME,np.sign(ME.mtd),Te,Tx)
print(" B. unconditional: always buy USD after the month-end fix")
rep("entry 16:00 exit 16:30",ME,one,960,990); rep("entry 16:05 exit 16:30",ME,one,965,990)
print(" C. split by the sign of SPX MTD (always-buy-USD trade)")
up=ME.mtd>0
rep("SPX up months: buy USD 16:00-16:30",ME[up],one[up],960,990); rep("SPX down months: buy USD 16:00-16:30",ME[~up],one[~up],960,990)
print(" D. signed against the 15:00->16:00 move (the lab's B1 sign)")
pre=np.sign(((ME.b960+ME.a960)/(ME.b900+ME.a900)-1)*ME.u)   # USD move in the hour before
rep("fade prior hour, 16:00-16:30",ME,-pre,960,990)
print(" E. agreement cases: SPX sign vs fade-prior-hour")
ag=(np.sign(ME.mtd)==-pre)
rep("both agree",ME[ag],np.sign(ME.mtd)[ag],960,990); rep("disagree (follow SPX sign)",ME[~ag],np.sign(ME.mtd)[~ag],960,990)
print(" F. by period, rule A entry 16:00 exit 16:30 / entry 16:05 exit 16:30")
for a,b in [('2013','2015'),('2016','2018'),('2019','2021')]:
    X=ME[(ME.index>=a)&(ME.index<str(int(b)+1))]
    rep(f"{a}-{b} e16:00",X,np.sign(X.mtd),960,990); rep(f"{a}-{b} e16:05",X,np.sign(X.mtd),965,990)
print(" G. by pair, rule A 16:00-16:30 (net bp, t)")
for s,X in ME.groupby('sym'):
    n,gr=trade(X,np.sign(X.mtd),960,990); print(f"    {s} n={len(n)} gross={gr.mean()*bp:6.2f} net={n.mean()*bp:6.2f} t={ts(n):5.2f} win={np.mean(n>0):.3f}")
print(" H. quarter-end vs other month-ends; |MTD| size")
rep("quarter-ends",ME[ME.q],np.sign(ME.mtd)[ME.q],960,990); rep("other month-ends",ME[~ME.q],np.sign(ME.mtd)[~ME.q],960,990)
for lo,hi in [(0,0.02),(0.02,0.04),(0.04,1)]:
    m=(ME.mtd.abs()>=lo)&(ME.mtd.abs()<hi); rep(f"|mtd| in [{lo},{hi})",ME[m],np.sign(ME.mtd)[m],960,990)
print(" I. other days of the month, rule A 16:00-16:30 (placebo / extension)")
for r in (1,2,3,5,10):
    X=A[A.rk==r]; rep(f"{r} weekdays before month-end",X,np.sign(X.mtd),960,990)
X=A[A.rk>=4]; rep("all days except last 4",X,np.sign(X.mtd),960,990)
print(" J. same clock time shifted: rule A on month-end at 15:00->15:30 and 17:00->18:00")
rep("15:00->15:45",ME,np.sign(ME.mtd),900,945); rep("17:00->18:00",ME,np.sign(ME.mtd),1020,1080)
