import numpy as np, pandas as pd
P='/home/user/gold-orb/lab/data/fp/'
m1=pd.read_parquet(P+'usdjpy_m1.parquet'); m1=m1[(m1.index>='2013-01-01')&(m1.index<'2022-01-01')]
mid=((m1.bc+m1.ac)/2).values; bid=m1.bc.values; ask=m1.ac.values; idx=m1.index
days=pd.date_range('2013-01-01','2021-12-31',freq='B')
def at(hm):
    t=pd.DatetimeIndex([pd.Timestamp(f"{d.date()} {hm}",tz='Asia/Tokyo') for d in days]).tz_convert('UTC')
    i=idx.searchsorted(t,side='left')-1
    ok=(i>=0)&((t-idx[np.clip(i,0,None)])<=pd.Timedelta(minutes=5))
    return i,ok
# gotobi: day-of-month multiple of 5 or last business day; if weekend -> previous business day
bd=set(days.date)
got=set()
for per in pd.period_range('2013-01','2021-12',freq='M'):
    last=per.days_in_month
    for dd in (5,10,15,20,25,last):
        d=pd.Timestamp(per.year,per.month,dd)
        while d.date() not in bd: d-=pd.Timedelta(days=1)
        got.add(d.date())
isg=np.array([d.date() in got for d in days])
i900,o1=at('09:00'); i955,o2=at('09:55'); i930,o0=at('09:30')
for exit_hm in ('10:30','11:00','11:55','13:00','15:00'):
    ix,o3=at(exit_hm)
    ok=o1&o2&o3&o0
    pre=(mid[i955]/mid[i900]-1)*1e4
    gross=-(mid[ix]/mid[i955]-1)*1e4            # short USDJPY at the fix
    net=(bid[i955]/ask[ix]-1)*1e4-0.2           # sell at bid, buy back at ask, 0.1bp slip per side
    y=days.year
    def line(lbl,m):
        m=m&ok; g=gross[m]; n_=net[m]
        if m.sum()<30: return
        by=' '.join(f"{yy%100}:{net[m&(y==yy)].mean():+.1f}" for yy in range(2013,2022))
        print(f"  exit {exit_hm} {lbl:28s} n={m.sum():4d} gross {g.mean():+.2f} (t {g.mean()/g.std(ddof=1)*np.sqrt(len(g)):+.1f}) net {n_.mean():+.2f} (t {n_.mean()/n_.std(ddof=1)*np.sqrt(len(n_)):+.1f}) win {np.mean(n_>0):.2f} sd {n_.std():.0f} | net by yr {by}")
    line('all days',np.ones(len(days),bool))
    line('gotobi',isg); line('not gotobi',~isg)
    line('pre(9:00-9:55) > +5bp',pre>5); line('pre in [0,5]',(pre>=0)&(pre<=5)); line('pre < 0',pre<0); line('pre < -5',pre<-5)
    line('gotobi & pre>0',isg&(pre>0))
print('--- pre-fix leg (long USDJPY) and minute-resolution placement of the turn')
for a_hm,b_hm,sg in (('08:00','09:55',1),('09:00','09:55',1),('09:30','09:55',1),('09:45','10:15',-1),('09:55','10:05',-1),('10:05','11:55',-1),('09:50','11:55',-1),('10:00','11:55',-1)):
    ia,oa=at(a_hm); ib,ob=at(b_hm); ok=oa&ob
    g=sg*(mid[ib]/mid[ia]-1)*1e4
    net=np.where(sg==1,(bid[ib]/ask[ia]-1),(bid[ia]/ask[ib]-1))*1e4-0.2
    for lbl,m in (('all',ok),('gotobi',ok&isg),('not gotobi',ok&~isg)):
        gg=g[m]; nn=net[m]
        print(f"  {a_hm}->{b_hm} {'long' if sg==1 else 'short'} {lbl:10s} n={m.sum()} gross {gg.mean():+.2f} (t {gg.mean()/gg.std(ddof=1)*np.sqrt(len(gg)):+.1f}) net {nn.mean():+.2f} (t {nn.mean()/nn.std(ddof=1)*np.sqrt(len(nn)):+.1f})")
print('--- resting sell-limit above the market before the fix (fill when BID touches), exit 11:55 JST at ask + 0.1bp; stop not modelled')
bh=m1.bh.values
ix,ox=at('11:55'); y=days.year
for start in ('09:30','09:45'):
    ia,oa=at(start); ie,oe=at('09:57')
    for x in (0,1,2,3,5,8):
        res=[];yy=[];gg=[]
        for k in range(len(days)):
            if not(oa[k] and oe[k] and ox[k]): continue
            L=mid[ia[k]]*(1+x/1e4)
            seg=bh[ia[k]+1:ie[k]+1]
            if len(seg) and seg.max()>=L:
                j=ia[k]+1+int(np.argmax(seg>=L))
                px=max(L, m1.bo.values[j])
                res.append((px/ask[ix[k]]-1)*1e4-0.1); yy.append(y[k]); gg.append(isg[k])
        r=np.array(res); yy=np.array(yy); gg=np.array(gg)
        by=' '.join(f"{v%100}:{r[yy==v].sum():+.0f}" for v in range(2013,2022))
        print(f"  from {start} limit +{x}bp: fills {len(r)} ({len(r)/9:.0f}/yr) net {r.mean():+.2f} bp (t {r.mean()/r.std(ddof=1)*np.sqrt(len(r)):+.1f}) win {np.mean(r>0):.2f} sd {r.std():.0f} worst {r.min():.0f} total/yr {r.sum()/9:+.0f} bp | gotobi net {r[gg].mean():+.2f} (n {gg.sum()}) | yearly total bp {by}")
print('--- placebo: same 2h short started at other clock times (JST), all weekdays, gross bp and t')
rows=[]
for hh in range(7,15):
    for mm in range(0,60,5):
        a=f"{hh:02d}:{mm:02d}"; b=f"{hh+2:02d}:{mm:02d}"
        ia,oa=at(a); ib,ob=at(b); ok=oa&ob
        g=-(mid[ib[ok]]/mid[ia[ok]]-1)*1e4
        rows.append((a,g.mean(),g.mean()/g.std(ddof=1)*np.sqrt(len(g))))
rows.sort(key=lambda r:-r[2])
print('  top 8 by t:',[(a,round(m,2),round(t,1)) for a,m,t in rows[:8]])
print('  bottom 4 by t:',[(a,round(m,2),round(t,1)) for a,m,t in rows[-4:]])
print('  rank of 09:55 among',len(rows),':',[i+1 for i,r in enumerate(rows) if r[0]=='09:55'])
print('--- summary stats of the simple rule (short 09:55, cover 11:55 JST), net of FP-frame spread + 0.2bp')
ix,ox=at('11:55'); ok=o2&ox
net=(bid[i955]/ask[ix]-1)*1e4-0.2
for lbl,m in (('A all weekdays',ok),('B gotobi',ok&isg)):
    s=pd.Series(net[m],index=days[m])
    cum=s.cumsum(); dd=(cum-cum.cummax()).min()
    mth=s.groupby([s.index.year,s.index.month]).sum()
    yr=s.groupby(s.index.year).sum()
    print(f"  {lbl}: n={len(s)} mean {s.mean():+.2f} sd {s.std():.1f} t {s.mean()/s.std()*np.sqrt(len(s)):+.1f} win {np.mean(s>0):.3f} worst {s.min():.0f} best {s.max():.0f} total {s.sum():.0f} bp; maxDD {dd:.0f} bp; months>0 {np.mean(mth>0):.2f}; yearly totals {dict(yr.round(0))}; annual Sharpe {s.mean()/s.std()*np.sqrt(len(s)/9):.2f}")
# cost sensitivity
for extra in (0.0,0.5,1.0):
    s=net[ok]-extra; g=net[ok&isg]-extra
    print(f"  extra cost {extra} bp: A net {s.mean():+.2f} (t {s.mean()/s.std()*np.sqrt(len(s)):+.1f}); B net {g.mean():+.2f} (t {g.mean()/g.std()*np.sqrt(len(g)):+.1f})")
spr=((m1.ac-m1.bc)/((m1.ac+m1.bc)/2)*1e4).values
print('  spread at entry bar: median %.2f mean %.2f p95 %.2f ; at exit: median %.2f'%(np.median(spr[i955[ok]]),spr[i955[ok]].mean(),np.percentile(spr[i955[ok]],95),np.median(spr[ix[ok]])))
print('--- robustness: drop the best day; winsorise at +/-60bp')
for lbl,m in (('A',ok),('B',ok&isg)):
    s=pd.Series(net[m],index=days[m]); print('  best day',lbl,s.idxmax().date(),round(s.max()))
    s2=s.drop(s.idxmax()); w=s.clip(-60,60)
    print(f"  {lbl} without best day: mean {s2.mean():+.2f} sd {s2.std():.1f} t {s2.mean()/s2.std()*np.sqrt(len(s2)):+.1f}; winsorised: mean {w.mean():+.2f} t {w.mean()/w.std()*np.sqrt(len(w)):+.1f}; median {s.median():+.2f}; years>0 without best day: {int((s2.groupby(s2.index.year).sum()>0).sum())}/9")
