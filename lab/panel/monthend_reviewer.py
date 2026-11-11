import sys; sys.dont_write_bytecode=True
sys.path.insert(0, "/home/user/gold-orb/lab")
import pandas as pd, numpy as np
import goldlab as gl
from goldlab import r2
bp=1e4
S="/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/"
def ts(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    return x.mean()/x.std(ddof=1)*np.sqrt(len(x)) if len(x)>2 else np.nan
g=pd.read_csv(S+"dl/DIX.csv",parse_dates=['date']).set_index('date'); g=g[g.index<"2022-01-01"]
px=g.price
pme=px.groupby(px.index.to_period('M')).last().shift(1)
pm=pd.Series(px.index.to_period('M').map(pme).values,index=px.index)
mtd_prev=(px.shift(1)/pm-1)
usd_dir={'eurusd':-1,'gbpusd':-1,'audusd':-1,'nzdusd':-1,'usdjpy':1,'usdcad':1,'usdchf':1}
Ts=list(range(930,1021))   # 15:30..17:00
rows=[]
for sym in usd_dir:
    m1=r2.load(sym, end="2022-01-01")
    assert m1.index[-1] < pd.Timestamp("2022-01-01", tz="UTC")
    ld=pd.DatetimeIndex(gl.local(m1.index, gl.LDN)).tz_localize(None)
    hm=ld.hour*60+ld.minute
    k=(hm>=930)&(hm<=1020)
    df=pd.DataFrame({'bo':m1.bo.values[k],'ao':m1.ao.values[k],'d':ld.normalize()[k],'hm':hm[k]})
    B=df.pivot_table(index='d',columns='hm',values='bo',aggfunc='first'); A_=df.pivot_table(index='d',columns='hm',values='ao',aggfunc='first')
    B=B.ffill(axis=1); A_=A_.ffill(axis=1)
    D=pd.concat({'b':B,'a':A_},axis=1); D=D[D.index.dayofweek<5].dropna()
    per=D.index.to_period('M')
    D[('x','rk')]=pd.Series(D.index,index=D.index).groupby(per).rank(ascending=False).values-1
    D[('x','mtd')]=mtd_prev.reindex(D.index); D[('x','sym')]=sym; D[('x','u')]=usd_dir[sym]
    # pair's own month-to-date USD move as of 15:30 today vs 16:00 of previous month's last day
    mid16=(D[('b',960)]+D[('a',960)])/2; lastm=mid16.groupby(per).last().shift(1)
    base=pd.Series(per.map(lastm).values,index=D.index)
    D[('x','usd_mtd')]=((D[('b',930)]+D[('a',930)])/2/base-1)*usd_dir[sym]
    rows.append(D); r2.free()
A=pd.concat(rows); A=A[A[('x','mtd')].notna()]
ME=A[A[('x','rk')]==0]
u=ME[('x','u')]; sg=np.sign(ME[('x','mtd')])
mid=(ME['b']+ME['a'])/2
# 1. sign-adjusted cumulative mid path relative to 16:00, averaged by date
path=(mid.div(mid[960],axis=0)-1).mul(u*sg,axis=0)*bp
pd_=path.groupby(level=0).mean()
print("sign-adjusted USD path (bp vs 16:00 mid), mean over dates:")
for T in (930,945,950,955,957,958,959,960,961,962,963,964,965,967,970,975,980,990,1005,1020):
    print(f"  {T//60}:{T%60:02d} {pd_[T].mean():+6.2f}  t={ts(pd_[T]):5.2f}")
# 2. spread in frame at entry minutes, month-end vs other days
sp=((A['a']-A['b'])/A['b']*bp)
for T in (945,960,962,965,990):
    print(f"frame spread bp at {T//60}:{T%60:02d}: month-end median {sp[T][A[('x','rk')]==0].median():.2f} mean {sp[T][A[('x','rk')]==0].mean():.2f} p90 {sp[T][A[('x','rk')]==0].quantile(.9):.2f} | other days median {sp[T][A[('x','rk')]>0].median():.2f}")
def net(X,dirn,Te,Tx):
    pos=dirn*X[('x','u')]
    ent=np.where(pos>0,X[('a',Te)],X[('b',Te)]); ext=np.where(pos>0,X[('b',Tx)],X[('a',Tx)])
    return pd.Series(pos*(ext/ent-1),index=X.index)
def rep(l,n):
    dn=n.groupby(level=0).mean(); print(f"  {l:50s} dates={len(dn)} net={dn.mean()*bp:+.2f} sd={dn.std()*bp:.2f} t={ts(dn):.2f} win={np.mean(dn>0):.3f}"); return dn
print("entry minute sensitivity (exit 16:30):")
for Te in (955,957,958,959,960,961,962,963,964,965,967,970): rep(f"entry {Te//60}:{Te%60:02d}",net(ME,sg,Te,990))
ME6=ME[ME[('x','sym')]!='usdjpy']; sg6=np.sign(ME6[('x','mtd')])
dn=rep("6 pairs frozen rule 16:00-16:30",net(ME6,sg6,960,990))
s=dn.sort_values(); print("   drop top5 dates: mean",round(s[:-5].mean()*bp,2),"t",round(ts(s[:-5]),2),"| top5 dates",[(d.strftime('%Y-%m'),round(v*bp,1)) for d,v in s[-5:].items()],"| worst5",[(d.strftime('%Y-%m'),round(v*bp,1)) for d,v in s[:5].items()])
print("   by year:",{y:round(v.mean()*bp,2) for y,v in dn.groupby(dn.index.year)})
# 3. alternative signs
usd_m=ME[('x','usd_mtd')]
bas=usd_m.groupby(level=0).transform('mean')
rep("sign = fade basket USD month-to-date (buy USD if USD down MTD)",net(ME,-np.sign(bas),960,990))
rep("sign = follow USD MTD",net(ME,np.sign(bas),960,990))
ag=np.sign(bas)==-sg
rep("SPX sign, when USD MTD agrees (USD down & SPX up etc.)",net(ME[ag],sg[ag],960,990)); rep("SPX sign, when USD-MTD fade disagrees",net(ME[~ag],sg[~ag],960,990))
print("corr(sign SPX mtd, -sign USD mtd) over dates:",np.corrcoef(sg.groupby(level=0).first(),-np.sign(bas).groupby(level=0).first())[0,1])
# 4. fade the 15:45->16:00 push and 15:30->16:00
for T0 in (930,945,955):
    pre=np.sign((mid[960]/mid[T0]-1)*u); rep(f"fade {T0//60}:{T0%60:02d}->16:00 own-pair move",net(ME,-pre,960,990))
    prb=np.sign(((mid[960]/mid[T0]-1)*u).groupby(level=0).transform('mean')); rep(f"fade {T0//60}:{T0%60:02d}->16:00 basket move",net(ME,-prb,960,990))
# 5. gross per-date distribution and up/down months since 2019
gr=((mid[990]/mid[960]-1)*u*sg).groupby(level=0).mean()
print("gross per date mean",round(gr.mean()*bp,2),"median",round(gr.median()*bp,2),"sd",round(gr.std()*bp,2))
m=ME[('x','mtd')].groupby(level=0).first()
for a,b in (('2013','2018'),('2019','2021')):
    x=dn[(dn.index>=a)&(dn.index<str(int(b)+1))]; mm=m.reindex(x.index)
    print(a,b,"up n",(mm>0).sum(),round(x[mm>0].mean()*bp,2),"down n",(mm<0).sum(),round(x[mm<0].mean()*bp,2),"|mtd|>=2% n",(mm.abs()>=.02).sum(),round(x[mm.abs()>=.02].mean()*bp,2),"<2% n",(mm.abs()<.02).sum(),round(x[mm.abs()<.02].mean()*bp,2))
# 6. holiday-ish dates: Dec month-ends, and good friday 2013-03-29, 2018-03-30
print("December month-ends:",round(dn[dn.index.month==12].mean()*bp,2),"n",(dn.index.month==12).sum())
