import json, os, csv, math
from datetime import datetime
import collections

YH='/tmp/yh5'
K=0.5
OR_BARS=6          # 09:00..09:25 -> first 30 min

def load_days(sym):
    fp=f'{YH}/{sym}.json'
    if not os.path.exists(fp): return None
    j=json.load(open(fp))
    res=j['chart']['result'][0]
    ts=res['timestamp']; q=res['indicators']['quote'][0]
    vol=q.get('volume')
    gmt=res['meta'].get('gmtoffset',32400)
    days=collections.defaultdict(list)
    for i,t in enumerate(ts):
        o,h,l,c=q['open'][i],q['high'][i],q['low'][i],q['close'][i]
        if None in (o,h,l,c): continue
        v=vol[i] if vol and vol[i] is not None else 0
        lt=datetime.utcfromtimestamp(t+gmt)
        hhmm=lt.hour*60+lt.minute
        if hhmm<540 or hhmm>930: continue
        days[lt.strftime('%Y-%m-%d')].append((hhmm,o,h,l,c,v))
    for d in days: days[d].sort()
    return days

syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append((row[1].strip(),row[2].strip()))
name={c:n for c,n in syms}

# ---- 1) characterise each stock: avg daily trading value & avg daily range% ----
prof={}
data={}
for s,_ in syms:
    if s=='^KS200': continue
    days=load_days(s)
    if not days or len(days)<30: continue
    data[s]=days
    tvals=[]; ranges=[]
    for d,bars in days.items():
        tv=sum(b[4]*b[5] for b in bars)             # close*volume per bar
        dh=max(b[2] for b in bars); dl=min(b[3] for b in bars); do=bars[0][1]
        tvals.append(tv)
        if do>0: ranges.append((dh-dl)/do)
    prof[s]=(sum(tvals)/len(tvals), sum(ranges)/len(ranges))

# composite rank: trading value (desc) + range% (desc)
syms_p=list(prof)
rv=sorted(syms_p,key=lambda s:prof[s][0],reverse=True)
rr=sorted(syms_p,key=lambda s:prof[s][1],reverse=True)
rankv={s:i for i,s in enumerate(rv)}
rankr={s:i for i,s in enumerate(rr)}
score={s:rankv[s]+rankr[s] for s in syms_p}
top=sorted(syms_p,key=lambda s:score[s])[:10]

print("=== Selected top-10 (거래대금 + 변동성 composite) ===")
print(f"{'code':<11}{'name':<14}{'avg TV(억)':>12}{'avg range%':>12}")
for s in top:
    tv,rg=prof[s]
    print(f"{s:<11}{name.get(s,''):<14}{tv/1e8:>12.0f}{rg*100:>11.2f}%")

# ---- 2) 30-min ORB on the 10 names ----
daily=collections.defaultdict(list); o2c=collections.defaultdict(list)
for s in top:
    for d,bars in data[s].items():
        if len(bars)<OR_BARS+2: continue
        oref=bars[0][1]
        orh=max(b[2] for b in bars[:OR_BARS]); orl=min(b[3] for b in bars[:OR_BARS])
        R=orh-orl
        if R<=0 or oref<=0: continue
        target=oref+K*R; last_close=bars[-1][4]
        o2c[d].append(last_close/oref-1)
        entry=None
        for b in bars[OR_BARS:]:
            if b[2]>=target: entry=max(target,b[1]); break
        if entry and entry>0: daily[d].append(last_close/entry-1)

dates=sorted(set(list(daily)+list(o2c)))
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

alltr=[x for v in daily.values() for x in v]; wins=sum(1 for x in alltr if x>0)
bh=[ (sum(o2c[d])/len(o2c[d])) if o2c.get(d) else 0 for d in dates]
beq=1.0;bcur=[]
for r in bh: beq*=(1+r);bcur.append(beq)

print()
print(f"days {len(dates)} ({dates[0]}~{dates[-1]}) | OR=30min | trades={len(alltr)} | avg {sum(len(daily[d]) for d in dates)/len(dates):.1f}/day | win {wins/len(alltr)*100:.1f}%")
print(f"mean gross trade: {sum(alltr)/len(alltr)*100:.3f}%")
print()
sc={'Gross':0.0,'Net@0.10%':0.001,'Net@0.20%':0.002,'Net@0.35%':0.0035}
R={k:run(c) for k,c in sc.items()}; S={k:stats(*R[k]) for k in sc}; bs=stats(bcur,bh)
print(f"{'METRIC':<13}"+"".join(f"{k:>12}" for k in sc)+f"{'IntraBH10':>12}")
print('-'*73)
def row(l,f): print(f"{l:<13}"+"".join(f"{f(S[k]):>12}" for k in sc)+f"{f(bs):>12}")
row('Total ret',lambda s:f"{s[0]*100:.1f}%")
row('CAGR',lambda s:f"{s[1]*100:.1f}%")
row('MDD',lambda s:f"{s[2]*100:.1f}%")
row('Sharpe',lambda s:f"{s[3]:.2f}")
row('Avg daily',lambda s:f"{s[4]*100:.3f}%")
json.dump({'dates':dates,'gross':R['Gross'][0],'net20':R['Net@0.20%'][0],
           'net35':R['Net@0.35%'][0],'bh':bcur,'top':[(s,name.get(s,'')) for s in top]},
          open('/tmp/intraday10_result.json','w'))
