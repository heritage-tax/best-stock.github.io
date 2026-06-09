import json, os, math
from datetime import datetime, timezone

YH='/tmp/yh'
def load(sym):
    j=json.load(open(f'{YH}/{sym}.json')); res=j['chart']['result'][0]
    ts=res['timestamp']; q=res['indicators']['quote'][0]
    adj=res['indicators']['adjclose'][0]['adjclose'] if 'adjclose' in res['indicators'] else None
    out={}
    for i,t in enumerate(ts):
        c=q['close'][i]
        if c is None or c<=0: continue
        if adj and adj[i] is not None: c=adj[i]
        d=datetime.fromtimestamp(t,tz=timezone.utc).strftime('%Y-%m-%d')
        out[d]=c
    return out

A=load('005930.KS'); B=load('000660.KS'); IDX=load('^KS200')
dates=sorted(set(A)&set(B)&set(IDX))
la=[math.log(A[d]) for d in dates]; lb=[math.log(B[d]) for d in dates]
pa=[A[d] for d in dates]; pb=[B[d] for d in dates]; pi=[IDX[d] for d in dates]

W=60         # regression / z-score window
ENTRY=2.0; EXIT=0.5; STOP=3.5

def ols(y,x):
    n=len(x); mx=sum(x)/n; my=sum(y)/n
    sxx=sum((xi-mx)**2 for xi in x); sxy=sum((x[i]-mx)*(y[i]-my) for i in range(n))
    b=sxy/sxx if sxx>0 else 0; a=my-b*mx
    resid=[y[i]-(a+b*x[i]) for i in range(n)]
    sd=(sum(r*r for r in resid)/n)**0.5
    return a,b,sd

# build z-score series using ONLY past window [t-W, t)
z=[None]*len(dates); beta=[None]*len(dates)
for t in range(W,len(dates)):
    a,b,sd=ols(la[t-W:t], lb[t-W:t])
    spread=la[t]-(a+b*lb[t])
    z[t]= spread/sd if sd>0 else 0
    beta[t]=b

def backtest(cost):
    pos=0; eq=1.0; cur=[]; rets=[]; ntr=0; wins=0; trade_pnl=0.0; cur_open=None
    for t in range(W+1,len(dates)):
        # decide position from z[t-1] (info available at close t-1), earn return on day t
        zz=z[t-1]
        newpos=pos
        if pos==0:
            if zz>=ENTRY: newpos=-1     # spread high -> short A long B
            elif zz<=-ENTRY: newpos=+1  # spread low  -> long A short B
        else:
            if pos==1 and (zz>=-EXIT or zz<=-STOP): newpos=0
            if pos==-1 and (zz<=EXIT or zz>=STOP): newpos=0
        # market returns day t
        rA=pa[t]/pa[t-1]-1; rB=pb[t]/pb[t-1]-1
        r = pos*(0.5*rA-0.5*rB)         # dollar-neutral long/short
        c = cost if newpos!=pos else 0.0
        r-=c
        eq*=(1+r); rets.append(r); cur.append(eq)
        # trade accounting
        if newpos!=pos:
            if pos!=0:  # closing
                ntr+=1; wins+=(1 if trade_pnl>0 else 0)
            if newpos!=0: trade_pnl=0.0
        if pos!=0: trade_pnl+=pos*(0.5*rA-0.5*rB)
        pos=newpos
    return cur,rets,ntr,wins

def stats(cur,rets):
    yrs=len(cur)/252; total=cur[-1]-1; cagr=cur[-1]**(1/yrs)-1
    peak=-1;mdd=0
    for v in cur: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets); sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0)

# benchmark stats
base=pi[W+1]; bench=[pi[t]/base for t in range(W+1,len(dates))]
bret=[bench[k]/bench[k-1]-1 for k in range(1,len(bench))]
def bh(p):
    b=p[W+1]; cur=[p[t]/b for t in range(W+1,len(dates))]; r=[cur[k]/cur[k-1]-1 for k in range(1,len(cur))]
    return stats(cur,r)

print(f"PAIRS: Samsung(005930) vs SK Hynix(000660) | {dates[W+1]} ~ {dates[-1]} ({len(dates)-W-1} days)")
print(f"window={W} entry|z|>={ENTRY} exit|z|<={EXIT} stop|z|>={STOP} | dollar-neutral 50/50")
print(f"avg hedge beta: {sum(b for b in beta if b)/(sum(1 for b in beta if b)):.2f}")
print()
print(f"{'scenario':<16}{'Total':>9}{'CAGR':>8}{'MDD':>8}{'Sharpe':>8}{'Trades':>8}{'Win%':>7}")
print('-'*64)
for c,lbl in [(0.0,'Gross'),(0.001,'Net@0.10%/chg'),(0.002,'Net@0.20%/chg'),(0.004,'Net@0.40%/chg')]:
    cur,rets,ntr,wins=backtest(c); s=stats(cur,rets)
    print(f"{lbl:<16}{s[0]*100:>8.1f}%{s[1]*100:>7.1f}%{s[2]*100:>7.1f}%{s[3]:>8.2f}{ntr:>8}{(wins/ntr*100 if ntr else 0):>6.1f}%")
    if c==0.002: best=(cur,rets)
print()
bs=stats(bench,bret)
print(f"{'KOSPI200 B&H':<16}{bs[0]*100:>8.1f}%{bs[1]*100:>7.1f}%{bs[2]*100:>7.1f}%{bs[3]:>8.2f}")
print(f"{'Samsung B&H':<16}{bh(pa)[0]*100:>8.1f}%{bh(pa)[1]*100:>7.1f}%{bh(pa)[2]*100:>7.1f}%{bh(pa)[3]:>8.2f}")
print(f"{'SK Hynix B&H':<16}{bh(pb)[0]*100:>8.1f}%{bh(pb)[1]*100:>7.1f}%{bh(pb)[2]*100:>7.1f}%{bh(pb)[3]:>8.2f}")

# market-neutrality: beta of strategy daily returns to KOSPI200 daily returns
cur,rets,_,_=backtest(0.002)
sr=rets[1:]  # align with bret length
n=min(len(sr),len(bret)); sr=sr[:n]; br=bret[:n]
mb=sum(br)/n; ms=sum(sr)/n
covb=sum((br[i]-mb)*(sr[i]-ms) for i in range(n))/n; varb=sum((x-mb)**2 for x in br)/n
print(f"\nStrategy beta to KOSPI200: {covb/varb:+.3f}  (≈0 => market-neutral)")

# split by regime
SPLIT='2025-05-31'
for rg,lo,hi in [('SIDEWAYS',dates[0],SPLIT),('BULL',SPLIT,dates[-1])]:
    cur=[];rets=[];eq=1.0;pos=0
    for t in range(W+1,len(dates)):
        if not (lo< dates[t] <=hi): continue
        zz=z[t-1]; newpos=pos
        if pos==0:
            if zz>=ENTRY:newpos=-1
            elif zz<=-ENTRY:newpos=+1
        else:
            if pos==1 and (zz>=-EXIT or zz<=-STOP):newpos=0
            if pos==-1 and (zz<=EXIT or zz>=STOP):newpos=0
        rA=pa[t]/pa[t-1]-1;rB=pb[t]/pb[t-1]-1
        r=pos*(0.5*rA-0.5*rB)-(0.002 if newpos!=pos else 0)
        eq*=(1+r);rets.append(r);cur.append(eq);pos=newpos
    if cur:
        s=stats(cur,rets)
        print(f"[{rg:<8}] Net@0.20% total {s[0]*100:+6.1f}%  Sharpe {s[3]:5.2f}  MDD {s[2]*100:5.1f}%  ({len(cur)}d)")
json.dump({'dates':[dates[t] for t in range(W+1,len(dates))],'eq':best[0],'bench':bench,'z':[z[t] for t in range(W+1,len(dates))]},open('/tmp/pairs_result.json','w'))
