import json, os, csv, math
from datetime import datetime, timezone

YH='/tmp/yh'   # 3y daily

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

idx=load('^KS200'); idx_close={r[0]:r[4] for r in idx}; idx_dates=[r[0] for r in idx]

syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

# build per-date records: for each date t, list of (sym, overnight_ret, intraday_ret)
# overnight = O_t / C_{t-1} - 1 ; intraday = C_t / O_t - 1
byday={}
loaded=0
for s in syms:
    rows=load(s)
    if not rows or len(rows)<100: continue
    loaded+=1
    for i in range(1,len(rows)):
        d,o,h,l,c=rows[i]; pc=rows[i-1][4]
        if pc<=0 or o<=0: continue
        on=o/pc-1; intra=c/o-1
        byday.setdefault(d,[]).append((s,on,intra))

dates=sorted(byday)

def backtest(N, direction, cost):
    """direction: 'mr'=buy most-negative overnight; 'mom'=buy most-positive overnight.
       buy at open, sell at close. equal weight top-N. returns equity curve & daily rets."""
    eq=1.0; cur=[]; rets=[]; ntr=0; wins=0
    for d in dates:
        recs=byday[d]
        if len(recs)<N:
            rets.append(0.0); cur.append(eq); continue
        recs_sorted=sorted(recs,key=lambda x:x[1])           # ascending overnight
        pick = recs_sorted[:N] if direction=='mr' else recs_sorted[-N:]
        trs=[p[2]-cost for p in pick]                        # intraday return minus cost
        for p in pick:
            ntr+=1; wins+= (1 if p[2]>0 else 0)
        r=sum(trs)/len(trs)
        eq*=(1+r); rets.append(r); cur.append(eq)
    return cur,rets,ntr,wins

def stats(cv,rets):
    yrs=len(cv)/252; total=cv[-1]-1; cagr=cv[-1]**(1/yrs)-1
    peak=-1;mdd=0
    for v in cv: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets); sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0)

# KOSPI200 benchmark
bdates=[d for d in dates if d in idx_close]; base=idx_close[bdates[0]]
bench=[idx_close[d]/base for d in bdates]; brets=[bench[k]/bench[k-1]-1 for k in range(1,len(bench))]
bs=stats(bench,brets)

print(f"MEAN-REVERSION (buy big overnight DROP at open, sell at close) | {loaded} stocks")
print(f"Period {dates[0]}~{dates[-1]} ({len(dates)} days, {len(dates)/252:.2f}y)")
print()
for N in [5,10,20]:
    cv,rets,ntr,wins=backtest(N,'mr',0.0)
    print(f"--- worst-{N} overnight, MEAN REVERSION ---  trades={ntr} intraday-win={wins/ntr*100:.1f}%")
    print(f"{'':<12}{'Gross':>11}{'Net@0.20%':>11}{'Net@0.35%':>11}{'KOSPI200':>11}")
    res={}
    for c,lbl in [(0.0,'Gross'),(0.002,'Net@0.20%'),(0.0035,'Net@0.35%')]:
        res[lbl]=stats(*backtest(N,'mr',c)[:2])
    for li,(lbl,f) in enumerate([('Total',lambda s:f"{s[0]*100:.1f}%"),('CAGR',lambda s:f"{s[1]*100:.1f}%"),
                                  ('MDD',lambda s:f"{s[2]*100:.1f}%"),('Sharpe',lambda s:f"{s[3]:.2f}")]):
        line=f"{lbl:<12}"+"".join(f"{f(res[k]):>11}" for k in ['Gross','Net@0.20%','Net@0.35%'])
        line+=f"{f(bs):>11}"
        print(line)
    print()

# contrast: momentum (buy biggest overnight GAINERS)
print("=== CONTRAST: MOMENTUM (buy best-overnight gainers, sell at close) ===")
for N in [5,10,20]:
    cv,rets,ntr,wins=backtest(N,'mom',0.0)
    s=stats(cv,rets)
    sn=stats(*backtest(N,'mom',0.002)[:2])
    print(f"top-{N}: Gross total {s[0]*100:6.1f}% CAGR {s[1]*100:6.1f}% Sharpe {s[3]:5.2f} | Net@0.20% total {sn[0]*100:6.1f}%  (intraday-win {wins/ntr*100:.1f}%)")

# save best MR (N=10) curve for chart
cvg=backtest(10,'mr',0.0)[0]; cvn=backtest(10,'mr',0.002)[0]
json.dump({'dates':dates,'mr_g':cvg,'mr_n20':cvn,'bdates':bdates,'bench':bench},open('/tmp/mr_result.json','w'))
