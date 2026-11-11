import pandas as pd, numpy as np, json
d=pd.read_parquet('/home/user/gold-orb/lab/data/fp/usdjpy_m1.parquet')
d=d[d.index<'2022-01-01']
d['mo']=(d.bo+d.ao)/2; d['mc']=(d.bc+d.ac)/2
d['spr_bp']=(d.ac-d.bc)/d.mc*1e4
d['spro_bp']=(d.ao-d.bo)/d.mo*1e4
print('spec', json.load(open('/home/user/gold-orb/lab/r2/fp_costs.json')).get('usdjpy'))
hm=d.index.hour*60+d.index.minute
# spread by minute around the fix
for m in [0*60+30,0*60+50,0*60+54,0*60+55,0*60+56,1*60,2*60+55,6*60,13*60]:
    s=d.spr_bp[hm==m]; so=d.spro_bp[hm==m]
    print('min %02d:%02d spread close med %.3f mean %.3f | open med %.3f mean %.3f p90 %.3f'%(m//60,m%60,s.median(),s.mean(),so.median(),so.mean(),so.quantile(.9)))
print('overall med', d.spr_bp.median())
def px(col, hhmm):
    s=d[col][hm==hhmm]; s.index=s.index.normalize(); return s
days=pd.DataFrame({
 'bo55':px('bo',55),'ao55':px('ao',55),'mo55':px('mo',55),
 'bo0255':px('bo',175),'ao0255':px('ao',175),'mo0255':px('mo',175),
 'mo30':px('mo',30),'mo105':px('mo',65),'mo56':px('mo',56),'mo100':px('mo',60),'mo50':px('mo',50),'bo100':px('bo',60),'bo56':px('bo',56),'bo57':px('bo',57),
 'mo0355':px('mo',235),'mo0555':px('mo',355),
}).dropna(subset=['bo55','ao0255'])
days=days[days.index.dayofweek<5]
days['gross']=-(days.mo0255/days.mo55-1)*1e4
days['net']=-(days.ao0255/days.bo55-1)*1e4-0.2   # plus commission? check spec
days['net_1mlate']=-(days.ao0255/days.bo56-1)*1e4-0.2
days['net_2mlate']=-(days.ao0255/days.bo57-1)*1e4-0.2
days['net_5mlate']=-(days.ao0255/days.bo100-1)*1e4-0.2
days['pre']=(days.mo55/days.mo30-1)*1e4
days['post10']=(days.mo105/days.mo55-1)*1e4
days['m1']=(days.mo56/days.mo55-1)*1e4
def st(x):
    x=x.dropna(); return 'n %d mean %+.2f t %.1f win %.0f%%'%(len(x),x.mean(),x.mean()/x.std()*np.sqrt(len(x)),(x>0).mean()*100)
print('A gross',st(days.gross)); print('A net',st(days.net))
for c in ['net_1mlate','net_2mlate','net_5mlate','pre','post10','m1']: print(c,st(days[c]))
print('cost implied', (days.gross-days.net).median(), (days.gross-days.net).mean())
# gotobi
def gotobi(idx):
    out=[]
    s=set(idx)
    for dt in idx:
        pass
    return out
dom=days.index.day
eom=days.index.is_month_end
# shift weekend gotobi to previous business day
alld=pd.date_range(days.index.min(),days.index.max(),tz='UTC')
g=[x for x in alld if x.day in (5,10,15,20,25) or x.is_month_end]
gs=set()
for x in g:
    while x.dayofweek>=5: x=x-pd.Timedelta(days=1)
    gs.add(x)
days['got']=days.index.isin(gs)
print('B gross',st(days.gross[days.got])); print('B net',st(days.net[days.got]))
print('nonB gross',st(days.gross[~days.got])); print('nonB net',st(days.net[~days.got]))
a=days.gross[days.got]; b=days.gross[~days.got]
print('diff t', (a.mean()-b.mean())/np.sqrt(a.var()/len(a)+b.var()/len(b)))
print(days.groupby(days.index.year).agg(n=('net','size'),gross=('gross','mean'),net=('net','mean'),tot=('net','sum'),pre=('pre','mean'),post10=('post10','mean')).round(2))
print(days[~days.got].groupby(days[~days.got].index.year).agg(n=('net','size'),gross=('gross','mean'),net=('net','mean')).round(2))
print(days[days.got].groupby(days[days.got].index.year).agg(n=('net','size'),gross=('gross','mean'),net=('net','mean')).round(2))
for lab,sel in [('2013-16',days.index.year<=2016),('2017-21',days.index.year>=2017),('2018-21',days.index.year>=2018),('2014-15,18-19,21',days.index.year.isin([2014,2015,2018,2019,2021]))]:
    print(lab,'A gross',st(days.gross[sel]),'| net',st(days.net[sel]),'| B net',st(days.net[sel&days.got]))
print('by dow', days.groupby(days.index.dayofweek).gross.agg(['size','mean']).round(2))
# winsorised/median robust
print('median gross',days.gross.median(),'median net',days.net.median())
x=days.net.sort_values(); print('top5',x.tail(5).round(0).to_dict()); print('net ex top 5 days',st(x.iloc[:-5])); print('net ex top 1%',st(x.iloc[:-23]))
# skew: sum of top 23 days vs total
print('total',x.sum(),'top23',x.tail(23).sum(),'bottom23',x.head(23).sum())
days.to_pickle('days.pkl')
