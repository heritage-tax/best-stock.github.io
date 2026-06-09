import json, os, csv, math
from datetime import datetime
import collections

YH='/tmp/yh5'; K=0.5; OR_BARS=6   # 30-min opening range

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

def wk(d):  # ISO year-week key
    y,w,_=datetime.strptime(d,'%Y-%m-%d').isocalendar(); return (y,w)

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

# per (stock, week): avg trading value, avg range%, and trade days
wkstats=collections.defaultdict(dict)   # week -> {stock: (tv, rng)}
wkdays=collections.defaultdict(lambda: collections.defaultdict(list))  # week->stock->[dates]
alldates=set()
for s,days in data.items():
    byw=collections.defaultdict(list)
    for d,bars in days.items():
        alldates.add(d); byw[wk(d)].append((d,bars))
    for w,items in byw.items():
        tvs=[]; rgs=[]
        for d,bars in items:
            tvs.append(sum(b[4]*b[5] for b in bars))
            do=bars[0][1]; dh=max(b[2] for b in bars); dl=min(b[3] for b in bars)
            if do>0: rgs.append((dh-dl)/do)
            wkdays[w][s].append(d)
        if tvs and rgs:
            wkstats[w][s]=(sum(tvs)/len(tvs), sum(rgs)/len(rgs))

weeks=sorted(wkstats)
def select_top(week):
    st=wkstats[week]; ss=list(st)
    rv=sorted(ss,key=lambda s:st[s][0],reverse=True); rr=sorted(ss,key=lambda s:st[s][1],reverse=True)
    iv={s:i for i,s in enumerate(rv)}; ir={s:i for i,s in enumerate(rr)}
    return sorted(ss,key=lambda s:iv[s]+ir[s])[:10]

def trade_day(bars):
    if len(bars)<OR_BARS+2: return None,None
    oref=bars[0][1]
    orh=max(b[2] for b in bars[:OR_BARS]); orl=min(b[3] for b in bars[:OR_BARS])
    R=orh-orl; last=bars[-1][4]
    o2c=last/oref-1
    if R<=0 or oref<=0: return None,o2c
    target=oref+K*R; entry=None
    for b in bars[OR_BARS:]:
        if b[2]>=target: entry=max(target,b[1]); break
    return (last/entry-1 if entry and entry>0 else None), o2c

# walk forward: test week i uses selection from week i-1
daily=collections.defaultdict(list); o2cd=collections.defaultdict(list)
picks_log=[]
for i in range(1,len(weeks)):
    selw=weeks[i-1]; testw=weeks[i]
    top=select_top(selw)
    picks_log.append((testw,[ (s,name.get(s,'')) for s in top]))
    for s in top:
        if s not in data: continue
        for d in wkdays[testw].get(s,[]):
            tr,o2c=trade_day(data[s][d])
            if o2c is not None: o2cd[d].append(o2c)
            if tr is not None: daily[d].append(tr)

dates=sorted(set(list(daily)+list(o2cd)))
def run(cost):
    eq=1.0;cur=[];rets=[]
    for d in dates:
        trs=daily.get(d,[]); r=(sum(trs)/len(trs)-cost) if trs else 0.0
        eq*=(1+r);rets.append(r);cur.append(eq)
    return cur,rets
def stats(cv,rets):
    yrs=len(cv)/252; total=cv[-1]-1; cagr=cv[-1]**(1/yrs)-1 if yrs>0 else 0
    peak=-1;mdd=0
    for v in cv: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets); sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0),m

# KOSPI200 benchmark over same test dates (daily close from 5m index)
idx=load_days('^KS200'); idxc={d:bars[-1][4] for d,bars in idx.items()}
bdates=[d for d in dates if d in idxc]; base=idxc[bdates[0]]
bench=[idxc[d]/base for d in bdates]
brets=[bench[k]/bench[k-1]-1 for k in range(1,len(bench))]

alltr=[x for v in daily.values() for x in v]; wins=sum(1 for x in alltr if x>0)
bh=[ (sum(o2cd[d])/len(o2cd[d])) if o2cd.get(d) else 0 for d in dates]
beq=1.0;bcur=[]
for r in bh: beq*=(1+r);bcur.append(beq)

print(f"WALK-FORWARD | test weeks: {len(weeks)-1} | days {len(dates)} ({dates[0]}~{dates[-1]})")
print(f"trades={len(alltr)} | avg {sum(len(daily[d]) for d in dates)/len(dates):.1f}/day | win {wins/len(alltr)*100:.1f}% | mean gross/trade {sum(alltr)/len(alltr)*100:.3f}%")
print()
sc={'Gross':0.0,'Net@0.10%':0.001,'Net@0.20%':0.002,'Net@0.35%':0.0035}
R={k:run(c) for k,c in sc.items()}; S={k:stats(*R[k]) for k in sc}
bs=stats(bcur,bh); ks=stats(bench,brets)
print(f"{'METRIC':<13}"+"".join(f"{k:>12}" for k in sc)+f"{'DynBH10':>12}{'KOSPI200':>12}")
print('-'*97)
def row(l,f,extra): print(f"{l:<13}"+"".join(f"{f(S[k]):>12}" for k in sc)+f"{f(bs):>12}{f(extra):>12}")
row('Total ret',lambda s:f"{s[0]*100:.1f}%",ks)
row('CAGR',lambda s:f"{s[1]*100:.1f}%",ks)
row('MDD',lambda s:f"{s[2]*100:.1f}%",ks)
row('Sharpe',lambda s:f"{s[3]:.2f}",ks)
row('Avg daily',lambda s:f"{s[4]*100:.3f}%",ks)
print()
print("=== weekly picks (test week -> selected from prior week) ===")
for testw,ps in picks_log:
    print(f"{testw}: "+", ".join(n or c for c,n in ps))
json.dump({'dates':dates,'gross':R['Gross'][0],'net20':R['Net@0.20%'][0],
           'net35':R['Net@0.35%'][0],'bh':bcur,'bdates':bdates,'bench':bench},
          open('/tmp/wf_result.json','w'))
