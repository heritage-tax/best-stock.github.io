import json, os, csv, math
from datetime import datetime
import collections

YH='/tmp/yh5'; K=0.5; OR_BARS=6
INV='114800.KS'   # KODEX INVERSE (1x)

def load_days(sym):
    fp=f'{YH}/{sym}.json'
    if not os.path.exists(fp): return None
    j=json.load(open(fp)); res=j['chart']['result'][0]
    ts=res['timestamp']; q=res['indicators']['quote'][0]; vol=q.get('volume')
    gmt=res['meta'].get('gmtoffset',32400)
    days=collections.defaultdict(list)
    for i,t in enumerate(ts):
        o,h,l,c=q['open'][i],q['high'][i],q['low'][i],q['close'][i]
        if None in (o,h,l,c): continue
        v=vol[i] if vol and vol[i] is not None else 0
        lt=datetime.utcfromtimestamp(t+gmt); hhmm=lt.hour*60+lt.minute
        if hhmm<540 or hhmm>930: continue
        days[lt.strftime('%Y-%m-%d')].append((hhmm,o,h,l,c,v))
    for d in days: days[d].sort()
    return days

def wk(d):
    y,w,_=datetime.strptime(d,'%Y-%m-%d').isocalendar(); return (y,w)

def long_orb(bars):
    """30m opening-range upside breakout, buy at target, exit at close."""
    if len(bars)<OR_BARS+2: return None
    oref=bars[0][1]
    orh=max(b[2] for b in bars[:OR_BARS]); orl=min(b[3] for b in bars[:OR_BARS])
    R=orh-orl; last=bars[-1][4]
    if R<=0 or oref<=0: return None
    up=oref+K*R
    for b in bars[OR_BARS:]:
        if b[2]>=up:
            e=max(up,b[1]); return last/e-1
    return None

syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append((row[1].strip(),row[2].strip()))
name={c:n for c,n in syms}

data={}
for s,_ in syms:
    if s=='^KS200': continue
    d=load_days(s)
    if d and len(d)>=20: data[s]=d
inv=load_days(INV)

# weekly profiles for selection
wkstats=collections.defaultdict(dict); wkdays=collections.defaultdict(lambda: collections.defaultdict(list))
for s,days in data.items():
    byw=collections.defaultdict(list)
    for d,bars in days.items(): byw[wk(d)].append((d,bars))
    for w,items in byw.items():
        tvs=[];rgs=[]
        for d,bars in items:
            tvs.append(sum(b[4]*b[5] for b in bars))
            do=bars[0][1];dh=max(b[2] for b in bars);dl=min(b[3] for b in bars)
            if do>0: rgs.append((dh-dl)/do)
            wkdays[w][s].append(d)
        if tvs and rgs: wkstats[w][s]=(sum(tvs)/len(tvs),sum(rgs)/len(rgs))
weeks=sorted(wkstats)
def select_top(week):
    st=wkstats[week];ss=list(st)
    rv=sorted(ss,key=lambda s:st[s][0],reverse=True);rr=sorted(ss,key=lambda s:st[s][1],reverse=True)
    iv={s:i for i,s in enumerate(rv)};ir={s:i for i,s in enumerate(rr)}
    return sorted(ss,key=lambda s:iv[s]+ir[s])[:10]

# walk-forward LONG stock book (per-day list of trade returns)
Lbook=collections.defaultdict(list)
for i in range(1,len(weeks)):
    top=select_top(weeks[i-1]); testw=weeks[i]
    for s in top:
        if s not in data: continue
        for d in wkdays[testw].get(s,[]):
            r=long_orb(data[s][d])
            if r is not None: Lbook[d].append(r)

# inverse ETF ORB (one trade per day if triggered)
INVbook={}
for d,bars in inv.items():
    r=long_orb(bars)
    if r is not None: INVbook[d]=r

dates=sorted(set(list(Lbook)+list(INVbook)))

def sleeve_long(d,cost):
    trs=Lbook.get(d,[])
    return (sum(trs)/len(trs)-cost) if trs else 0.0
def sleeve_inv(d,cost):
    return (INVbook[d]-cost) if d in INVbook else 0.0

def build(fn):
    eq=1.0;cur=[];rets=[]
    for d in dates:
        r=fn(d); eq*=(1+r);rets.append(r);cur.append(eq)
    return cur,rets
def stats(cv,rets):
    yrs=len(cv)/252;total=cv[-1]-1;cagr=cv[-1]**(1/yrs)-1 if yrs>0 else 0
    peak=-1;mdd=0
    for v in cv: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets);sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0),m

books={
 'LONG stocks only':lambda c: (lambda d:sleeve_long(d,c)),
 'INVERSE only':     lambda c: (lambda d:sleeve_inv(d,c)),
 'COMBINED 50/50':   lambda c: (lambda d:0.5*sleeve_long(d,c)+0.5*sleeve_inv(d,c)),
}
sc={'Gross':0.0,'Net@0.10%':0.001,'Net@0.20%':0.002,'Net@0.35%':0.0035}

# trade-level diagnostics
ltr=[x for v in Lbook.values() for x in v]; itr=list(INVbook.values())
print(f"WF + INVERSE | days={len(dates)} ({dates[0]}~{dates[-1]})")
print(f"LONG: trades={len(ltr)} win={sum(1 for x in ltr if x>0)/len(ltr)*100:.1f}% mean={sum(ltr)/len(ltr)*100:.3f}%")
print(f"INVERSE: trade-days={len(itr)}/{len(dates)} win={sum(1 for x in itr if x>0)/len(itr)*100:.1f}% mean={sum(itr)/len(itr)*100:.3f}%")

curves={}
for nm,mk in books.items():
    print(f"\n## {nm}")
    print(f"{'':<10}"+"".join(f"{k:>11}" for k in sc))
    S={}
    for k,c in sc.items():
        cv,rets=build(mk(c)); S[k]=stats(cv,rets)
        if k=='Gross': curves[nm+'_g']=cv
        if k=='Net@0.20%': curves[nm+'_n20']=cv
    for lbl,idx,f in [('Total',0,lambda v:f"{v*100:.1f}%"),('CAGR',1,lambda v:f"{v*100:.1f}%"),
                      ('MDD',2,lambda v:f"{v*100:.1f}%"),('Sharpe',3,lambda v:f"{v:.2f}")]:
        print(f"{lbl:<10}"+"".join(f"{f(S[k][idx]):>11}" for k in sc))

idx=load_days('^KS200');idxc={d:bars[-1][4] for d,bars in idx.items()}
bd=[d for d in dates if d in idxc];base=idxc[bd[0]];bench=[idxc[d]/base for d in bd]
print('\nKOSPI200 over window:',f"{(bench[-1]-1)*100:.1f}%")
curves['dates']=dates;curves['bdates']=bd;curves['bench']=bench
json.dump(curves,open('/tmp/wfi_result.json','w'))
