import json, os, csv, math
from datetime import datetime, timezone

YH='/tmp/yh'
K=0.5

def load(sym):
    fp=f'{YH}/{sym}.json'
    if not os.path.exists(fp): return None
    j=json.load(open(fp))
    res=j['chart']['result'][0]
    ts=res['timestamp']; q=res['indicators']['quote'][0]
    adj=None
    if 'adjclose' in res['indicators']:
        adj=res['indicators']['adjclose'][0]['adjclose']
    rows=[]
    for i,t in enumerate(ts):
        o,h,l,c=q['open'][i],q['high'][i],q['low'][i],q['close'][i]
        if None in (o,h,l,c) or c<=0: continue
        if adj and adj[i] is not None:
            r=adj[i]/c; o,h,l,c=o*r,h*r,l*r,c*r
        d=datetime.fromtimestamp(t,tz=timezone.utc).strftime('%Y-%m-%d')
        rows.append((d,o,h,l,c))
    return rows

# benchmark KOSPI200
idx=load('^KS200')
idx_dates=[r[0] for r in idx]
idx_close={r[0]:r[4] for r in idx}

# universe
syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

# Larry Williams volatility breakout, K=0.5
#   target_t = Open_t + K*(High_{t-1} - Low_{t-1})
#   if High_t >= target_t  -> enter at target_t, EXIT at next day's Open (overnight hold)
#   gross trade return = Open_{t+1}/target_t - 1
# Portfolio: each day, equal-weight capital across ALL names triggered that day.
daily={}     # date -> list of gross trade returns
loaded=0
for s in syms:
    rows=load(s)
    if not rows or len(rows)<30: continue
    loaded+=1
    for i in range(1,len(rows)-1):
        d,o,h,l,c=rows[i]; _,po,ph,pl,pc=rows[i-1]; _,no,nh,nl,nc=rows[i+1]
        rng=ph-pl; target=o+K*rng
        if rng>0 and h>=target and target>0:
            daily.setdefault(d,[]).append(no/target-1)

dates=[d for d in sorted(set(idx_dates)) if d in idx_close]

def run(cost):
    eq=1.0; curve=[]; rets=[]
    for d in dates:
        trs=daily.get(d,[])
        r=(sum(trs)/len(trs)-cost) if trs else 0.0
        eq*=(1+r); rets.append(r); curve.append(eq)
    return curve,rets

def stats(cv,rets):
    years=len(cv)/252
    total=cv[-1]-1; cagr=cv[-1]**(1/years)-1
    peak=-1; mdd=0
    for v in cv:
        peak=max(peak,v); mdd=min(mdd,v/peak-1)
    mean=sum(rets)/len(rets)
    sd=(sum((x-mean)**2 for x in rets)/len(rets))**0.5
    sharpe=mean/sd*math.sqrt(252) if sd>0 else 0
    return total,cagr,mdd,sharpe

# benchmark buy & hold
base=idx_close[dates[0]]
bv=[idx_close[d]/base for d in dates]
brets=[bv[i]/bv[i-1]-1 for i in range(1,len(bv))]
b=stats(bv,brets)

scen={'Gross (0%)':0.0,'Net @0.15%':0.0015,'Net @0.30%':0.0030}
results={}
for nm,c in scen.items():
    cv,rets=run(c); results[nm]=(cv,stats(cv,rets))

trigcounts=[len(daily.get(d,[])) for d in dates]
alltr=[x for v in daily.values() for x in v]
wins=sum(1 for x in alltr if x>0)
years=len(dates)/252

print(f"Universe: {loaded} KOSPI200 constituents (static snapshot)")
print(f"Period  : {dates[0]} ~ {dates[-1]}  ({years:.2f}y, {len(dates)} trading days)")
print(f"Signal  : K=0.5 breakout, exit next-day open | trades={len(alltr)} | avg {sum(trigcounts)/len(trigcounts):.0f} names/day | win {wins/len(alltr)*100:.1f}%")
print()
hdr=f"{'METRIC':<16}" + "".join(f"{k:>14}" for k in scen) + f"{'KOSPI200':>14}"
print(hdr); print('-'*len(hdr))
def row(lbl,fn):
    line=f"{lbl:<16}"
    for nm in scen: line+=f"{fn(results[nm][1]):>14}"
    line+=f"{fn(b):>14}"; print(line)
row('Total return',lambda s:f"{s[0]*100:.1f}%")
row('CAGR',        lambda s:f"{s[1]*100:.1f}%")
row('MDD',         lambda s:f"{s[2]*100:.1f}%")
row('Sharpe',      lambda s:f"{s[3]:.2f}")
row('Final (x)',   lambda s:f"{ (s[0]+1):.2f}")

json.dump({'dates':dates,'bench':bv,
           'gross':results['Gross (0%)'][0],
           'net15':results['Net @0.15%'][0],
           'net30':results['Net @0.30%'][0],
           'trig':trigcounts,'loaded':loaded,
           'b':b,'g':results['Gross (0%)'][1],
           'n15':results['Net @0.15%'][1],'n30':results['Net @0.30%'][1]},
          open('/tmp/result.json','w'))
