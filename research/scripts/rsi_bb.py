import json, os, math
from datetime import datetime, timezone
import csv

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

syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

SPLIT='2025-05-31'
def regime(d): return 'SIDEWAYS' if d<=SPLIT else 'BULL'

def rsi_wilder(C,n=14):
    rsi=[None]*len(C)
    if len(C)<=n: return rsi
    gains=0; losses=0
    for i in range(1,n+1):
        ch=C[i]-C[i-1]; gains+=max(ch,0); losses+=max(-ch,0)
    ag=gains/n; al=losses/n
    rsi[n]=100-100/(1+ag/al) if al>0 else 100
    for i in range(n+1,len(C)):
        ch=C[i]-C[i-1]
        ag=(ag*(n-1)+max(ch,0))/n; al=(al*(n-1)+max(-ch,0))/n
        rsi[i]=100-100/(1+ag/al) if al>0 else 100
    return rsi

# Strategy: BUY when close < lower Bollinger(20,2) AND RSI(14) < RTHR (fresh entry).
# EXIT when close >= SMA20 (mean reversion) OR maxhold 15d OR stop -15%.
def event_study(RTHR, K=2.0, MAXHOLD=15):
    res={'SIDEWAYS':[], 'BULL':[]}
    for s in syms:
        rows=load(s)
        if not rows or len(rows)<60: continue
        C=[r[1] for r in rows]
        rsi=rsi_wilder(C,14)
        sma=[None]*len(C); low=[None]*len(C)
        for i in range(19,len(C)):
            w=C[i-19:i+1]; m=sum(w)/20
            sd=(sum((x-m)**2 for x in w)/20)**0.5
            sma[i]=m; low[i]=m-K*sd
        i=20
        while i<len(C)-1:
            if low[i] and rsi[i] is not None and sma[i]:
                sig = C[i]<low[i] and rsi[i]<RTHR
                prev_sig = (low[i-1] and rsi[i-1] is not None and C[i-1]<low[i-1] and rsi[i-1]<RTHR)
                if sig and not prev_sig:                 # fresh signal
                    entry=C[i]; rg=regime(rows[i][0]); ex=None
                    for j in range(i+1,min(i+1+MAXHOLD,len(C))):
                        if (sma[j] and C[j]>=sma[j]) or C[j]/entry-1<=-0.15:
                            ex=C[j]/entry-1; i=j; break
                    if ex is None:
                        ex=C[min(i+MAXHOLD,len(C)-1)]/entry-1; i=i+MAXHOLD
                    res[rg].append(ex)
            i+=1
    return res

print("RSI(14) + Bollinger(20,2) MEAN-REVERSION on KOSPI200 (178 stocks, 3y daily)")
print("BUY: close<lower band AND RSI<threshold | EXIT: close>=SMA20 or 15d or -15% stop | cost ~0.20%\n")
print(f"{'rule':<26}{'SIDEWAYS  n / mean / net / win':>40}{'BULL  n / mean / net / win':>40}")
def fmt(a):
    if not a: return f"{'(none)':>38}"
    m=sum(a)/len(a); w=sum(1 for x in a if x>0)/len(a)
    return f"n={len(a):4d}  {m*100:+5.2f}% / {m*100-0.2:+5.2f}% / {w*100:4.1f}%"
for RTHR in [25,30,35]:
    r=event_study(RTHR)
    print(f"close<LB & RSI<{RTHR:<2}        {fmt(r['SIDEWAYS']):>40}{fmt(r['BULL']):>40}")

# Connors-style: RSI(2)<10 + below lower band, exit on close>SMA5 (faster)
def rsi_simple(C,n=2):
    rsi=[None]*len(C)
    for i in range(n,len(C)):
        g=sum(max(C[k]-C[k-1],0) for k in range(i-n+1,i+1))/n
        l=sum(max(C[k-1]-C[k],0) for k in range(i-n+1,i+1))/n
        rsi[i]=100-100/(1+g/l) if l>0 else 100
    return rsi
def connors():
    res={'SIDEWAYS':[],'BULL':[]}
    for s in syms:
        rows=load(s)
        if not rows or len(rows)<60: continue
        C=[r[1] for r in rows]; rsi=rsi_simple(C,2)
        sma=[None]*len(C); low=[None]*len(C); sma5=[None]*len(C)
        for i in range(19,len(C)):
            w=C[i-19:i+1]; m=sum(w)/20; sd=(sum((x-m)**2 for x in w)/20)**0.5
            sma[i]=m; low[i]=m-2*sd
        for i in range(4,len(C)): sma5[i]=sum(C[i-4:i+1])/5
        i=20
        while i<len(C)-1:
            if low[i] and rsi[i] is not None:
                if C[i]<low[i] and rsi[i]<10:
                    entry=C[i]; rg=regime(rows[i][0]); ex=None
                    for j in range(i+1,min(i+11,len(C))):
                        if (sma5[j] and C[j]>sma5[j]) or C[j]/entry-1<=-0.15:
                            ex=C[j]/entry-1; i=j; break
                    if ex is None: ex=C[min(i+10,len(C)-1)]/entry-1; i=i+10
                    res[rg].append(ex)
            i+=1
    return res
c=connors()
print(f"\nConnors RSI(2)<10 & close<LB, exit close>SMA5:")
print(f"   SIDEWAYS {fmt(c['SIDEWAYS'])}   |   BULL {fmt(c['BULL'])}")
