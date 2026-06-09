import json, os, math
from datetime import datetime, timezone

YH='/tmp/yh'
def load(sym):
    fp=f'{YH}/{sym}.json'
    if not os.path.exists(fp): return None
    j=json.load(open(fp)); res=j['chart']['result'][0]
    ts=res['timestamp']; q=res['indicators']['quote'][0]
    adj=res['indicators']['adjclose'][0]['adjclose'] if 'adjclose' in res['indicators'] else None
    rows=[]
    for i,t in enumerate(ts):
        c=q['close'][i]
        if c is None or c<=0: continue
        if adj and adj[i] is not None: c=adj[i]
        d=datetime.fromtimestamp(t,tz=timezone.utc).strftime('%Y-%m-%d')
        rows.append((d,c))
    return rows

import csv
syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

SPLIT='2025-05-31'   # sideways(before) vs bull(after)
MAXHOLD=15           # swing: hold up to ~3 weeks
def regime(d): return 'SIDEWAYS' if d<=SPLIT else 'BULL'

# BNF rule: deviation = close/MA25 - 1. Enter when deviation crosses <= -X (oversold).
# Exit when deviation >= 0 (reverted to MA, "rebound") OR maxhold OR stop (deviation <= -X-0.15).
def event_study(X):
    res={'SIDEWAYS':[], 'BULL':[]}
    for s in syms:
        rows=load(s)
        if not rows or len(rows)<60: continue
        C=[r[1] for r in rows]
        ma=[None]*len(C)
        for i in range(24,len(C)): ma[i]=sum(C[i-24:i+1])/25
        i=25
        while i<len(C)-1:
            if ma[i] and ma[i-1]:
                dev=C[i]/ma[i]-1; devp=C[i-1]/ma[i-1]-1
                if dev<=-X and devp>-X:           # fresh cross below -X
                    entry=C[i]; rg=regime(rows[i][0]); exitret=None
                    for j in range(i+1,min(i+1+MAXHOLD,len(C))):
                        d2=C[j]/ma[j]-1 if ma[j] else -1
                        if d2>=0 or C[j]/entry-1<=-0.15:   # revert to MA or stop -15%
                            exitret=C[j]/entry-1; i=j; break
                    if exitret is None:
                        exitret=C[min(i+MAXHOLD,len(C)-1)]/entry-1; i=i+MAXHOLD
                    res[rg].append(exitret)
            i+=1
    return res

print("BNF-style deviation-rate CONTRARIAN (buy when close <= -X% below 25d MA, sell on reversion to MA / 15d / -15% stop)")
print("KOSPI200 178 stocks, 3y, by regime. Per-trade swing returns (gross). Cost ~0.20% round trip.\n")
print(f"{'threshold':<12}{'SIDEWAYS: n/mean/win':>34}{'BULL: n/mean/win':>34}")
for X in [0.15,0.20,0.25,0.30]:
    r=event_study(X)
    def fmt(a):
        if not a: return f"{'-':>32}"
        m=sum(a)/len(a); w=sum(1 for x in a if x>0)/len(a)
        return f"n={len(a):4d} mean={m*100:+6.2f}% net={m*100-0.2:+6.2f}% win={w*100:4.1f}%"
    print(f"dev<=-{int(X*100):2d}%   {fmt(r['SIDEWAYS']):>34}   {fmt(r['BULL']):>34}")
