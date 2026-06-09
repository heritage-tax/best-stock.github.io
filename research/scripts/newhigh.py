import json, os, csv, math
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
        o,h,l,c=q['open'][i],q['high'][i],q['low'][i],q['close'][i]
        if None in (o,h,l,c) or c<=0: continue
        if adj and adj[i] is not None:
            r=adj[i]/c; o,h,l,c=o*r,h*r,l*r,c*r
        d=datetime.fromtimestamp(t,tz=timezone.utc).strftime('%Y-%m-%d')
        rows.append((d,o,h,l,c))
    return rows

idx=load('^KS200'); idx_close={r[0]:r[4] for r in idx}
syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

# new high on day t (close-based): close_t == max(close over last N incl t) AND strictly > prior max
# then next day t+1: intraday = C/O-1, overnight = O/C_t-1
def run(N):
    perday_intra={}   # date(t+1) -> list of intraday rets
    trades_intra=[]; trades_on=[]; trades_full=[]
    for s in syms:
        rows=load(s)
        if not rows or len(rows)<N+10: continue
        closes=[r[4] for r in rows]
        for t in range(N,len(rows)-1):
            prior_max=max(closes[t-N:t])
            if closes[t] > prior_max:                  # fresh N-day high
                d1,o1,h1,l1,c1=rows[t+1]; ct=rows[t][4]
                if o1<=0 or ct<=0: continue
                intra=c1/o1-1; on=o1/ct-1; full=c1/ct-1
                perday_intra.setdefault(d1,[]).append(intra)
                trades_intra.append(intra); trades_on.append(on); trades_full.append(full)
    return perday_intra,trades_intra,trades_on,trades_full

def stats(cv,rets):
    yrs=len(cv)/252; total=cv[-1]-1; cagr=cv[-1]**(1/yrs)-1 if yrs>0 else 0
    peak=-1;mdd=0
    for v in cv: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets); sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0)

alldates=sorted(idx_close)
def equity(perday,cost):
    eq=1.0;cur=[];rets=[]
    for d in alldates:
        trs=perday.get(d,[])
        r=(sum(trs)/len(trs)-cost) if trs else 0.0
        eq*=(1+r);rets.append(r);cur.append(eq)
    return cur,rets

print("NEW-HIGH BREAKOUT -> next-day buy OPEN, sell CLOSE (intraday) | KOSPI200 3y")
print()
for N,lbl in [(20,'20-day'),(60,'60-day'),(252,'52-week')]:
    perday,ti,ton,tf=run(N)
    mi=sum(ti)/len(ti); mon=sum(ton)/len(ton); mf=sum(tf)/len(tf)
    wi=sum(1 for x in ti if x>0)/len(ti)
    print(f"### {lbl} new high  | breakout events={len(ti)} | intraday win={wi*100:.1f}%")
    print(f"   per-trade gross: INTRADAY(open->close)={mi*100:+.3f}%  OVERNIGHT(close->open)={mon*100:+.3f}%  FULL(close->close)={mf*100:+.3f}%")
    cvg,rg=equity(perday,0.0); cvn2=equity(perday,0.002)[0]; cvn3=equity(perday,0.003)[0]
    sg=stats(cvg,rg); s2=stats(cvn2,rg); s3=stats(cvn3,rg)
    print(f"   PORTFOLIO (buy all breakouts next day, EW, intraday):")
    print(f"      Gross   : total {sg[0]*100:7.1f}%  CAGR {sg[1]*100:6.1f}%  MDD {sg[2]*100:6.1f}%  Sharpe {sg[3]:.2f}")
    print(f"      Net@0.20%: total {s2[0]*100:7.1f}%  CAGR {s2[1]*100:6.1f}%  Sharpe {s2[3]:.2f}")
    print(f"      Net@0.30%: total {s3[0]*100:7.1f}%  CAGR {s3[1]*100:6.1f}%  Sharpe {s3[3]:.2f}")
    print()

base=idx_close[alldates[0]]
print(f"KOSPI200 B&H over window: {(idx_close[alldates[-1]]/base-1)*100:.1f}%")
