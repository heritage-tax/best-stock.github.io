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
alldates=sorted(idx_close)
syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

# per-date cross section: date -> list of dict signals (computed at close of t), with NEXT day returns
byday={}
for s in syms:
    rows=load(s)
    if not rows or len(rows)<260: continue
    C=[r[4] for r in rows]
    for t in range(252,len(rows)-1):
        ct=C[t]; o1=rows[t+1][1]; c1=rows[t+1][4]
        if ct<=0 or o1<=0: continue
        ot=rows[t][1]
        rec={
            'ret1': ct/C[t-1]-1,
            'ret5': ct/C[t-5]-1,
            'on':   o1/ct-1,        # overnight (close_t -> open_t+1)
            'intra':c1/o1-1,        # next-day intraday (open->close)
            'gap':  ot/C[t-1]-1 if ot>0 else 0,   # same-day open gap
            'intra0': ct/ot-1 if ot>0 else 0,     # same-day open->close
            'hi52': ct>max(C[t-252:t]),
            'hi20': ct>max(C[t-20:t]),
            'lo52': ct<min(C[t-252:t]),
        }
        byday.setdefault(rows[t][0],[]).append(rec)
dates=[d for d in alldates if d in byday]

def stats(cur,rets):
    yrs=len(cur)/252; total=cur[-1]-1; cagr=cur[-1]**(1/yrs)-1 if yrs>0 else 0
    peak=-1;mdd=0
    for v in cur: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets); sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0)

def techrun(selector, leg, side, cost, N=None):
    """selector(rec)->bool filter; if N given, rank by key. leg in {'on','intra'}; side +1 long/-1 short."""
    eq=1.0;cur=[];rets=[];ntr=0;wins=0
    for d in dates:
        recs=[r for r in byday[d] if selector(r)]
        if not recs: rets.append(0.0);cur.append(eq);continue
        if N: recs=recs[:N]
        trs=[]
        for r in recs:
            g=side*r[leg]-cost
            trs.append(g); ntr+=1; wins+=(1 if side*r[leg]>0 else 0)
        rr=sum(trs)/len(trs); eq*=(1+rr); rets.append(rr); cur.append(eq)
    return stats(cur,rets),ntr,(wins/ntr if ntr else 0)

# rank helpers: build per-day sorted picks for top/bottom-N by a key
def topN_run(key, N, biggest, leg, side, cost):
    eq=1.0;cur=[];rets=[];ntr=0;wins=0
    for d in dates:
        recs=byday[d]
        if len(recs)<N: rets.append(0.0);cur.append(eq);continue
        rs=sorted(recs,key=lambda r:r[key],reverse=biggest)[:N]
        trs=[side*r[leg]-cost for r in rs]
        for r in rs: ntr+=1; wins+=(1 if side*r[leg]>0 else 0)
        rr=sum(trs)/len(trs); eq*=(1+rr);rets.append(rr);cur.append(eq)
    return stats(cur,rets),ntr,(wins/ntr if ntr else 0)

C=0.002
techs=[]
# 1. All-stocks overnight (pure overnight anomaly)
techs.append(('All stocks: buy close, sell open (overnight)', techrun(lambda r:True,'on',1,C)))
# 2. 52wk high -> overnight (reference winner)
techs.append(('52wk-high breakout: overnight hold', techrun(lambda r:r['hi52'],'on',1,C)))
# 3. 20d high -> overnight
techs.append(('20d-high breakout: overnight hold', techrun(lambda r:r['hi20'],'on',1,C)))
# 4. Today top-20 gainers -> overnight (momentum overnight)
techs.append(('Top-20 daily gainers: overnight hold', topN_run('ret1',20,True,'on',1,C)))
# 5. Top-20 5d momentum -> overnight
techs.append(('Top-20 5d-momentum: overnight hold', topN_run('ret5',20,True,'on',1,C)))
# 6. >=+5% gap context: short gainers intraday (gainer fade)
techs.append(('Gap-up >=+5%: SHORT intraday (fade)', techrun(lambda r:r['ret1']>=0.05,'intra',-1,C)))
# 7. <=-10% crash -> next-day intraday buy (user winner #1)
techs.append(('Crash <=-10%: buy next-day intraday', techrun(lambda r:r['ret1']<=-0.10,'intra',1,C)))
# 8. <=-10% crash -> overnight hold
techs.append(('Crash <=-10%: overnight hold', techrun(lambda r:r['ret1']<=-0.10,'on',1,C)))
# 9. Worst-20 losers -> next-day intraday (daily reversal)
techs.append(('Worst-20 losers: buy next-day intraday', topN_run('ret1',20,False,'intra',1,C)))
# 10. Worst-20 losers -> overnight hold
techs.append(('Worst-20 losers: overnight hold', topN_run('ret1',20,False,'on',1,C)))
# 11. 52wk LOW -> next-day intraday (oversold bounce)
techs.append(('52wk-low: buy next-day intraday', techrun(lambda r:r['lo52'],'intra',1,C)))
# 12. 52wk LOW -> overnight hold
techs.append(('52wk-low: overnight hold', techrun(lambda r:r['lo52'],'on',1,C)))
# 13. Top-20 gainers -> next-day intraday (momentum intraday, expected bad)
techs.append(('Top-20 gainers: buy next-day intraday', topN_run('ret1',20,True,'intra',1,C)))
# 14. SAME-DAY gap-down <=-10% at open -> buy open sell same close (user winner #1)
techs.append(('Gap-DOWN open <=-10%: buy open, sell same close', techrun(lambda r:r['gap']<=-0.10,'intra0',1,C)))
# 15. SAME-DAY gap-up >=+5% at open -> short, cover same close (gainer fade)
techs.append(('Gap-UP open >=+5%: SHORT open, cover same close', techrun(lambda r:r['gap']>=0.05,'intra0',-1,C)))
# 16. SAME-DAY gap-up >=+3% -> short same close
techs.append(('Gap-UP open >=+3%: SHORT open, cover same close', techrun(lambda r:r['gap']>=0.03,'intra0',-1,C)))

# KOSPI200
base=idx_close[alldates[0]]; b_tot=idx_close[alldates[-1]]/base-1

rows_out=[]
for name,(st,ntr,win) in techs:
    rows_out.append((name,st[0],st[1],st[2],st[3],ntr,win))
rows_out.sort(key=lambda x:-x[1])   # sort by Net total

print(f"TECHNIQUE BATTERY | KOSPI200 178 stocks, 3y daily | NET @0.20% cost | ranked by total return")
print(f"(KOSPI200 buy&hold over window: {b_tot*100:+.1f}%)")
print()
print(f"{'#':<3}{'TECHNIQUE':<44}{'Net Total':>10}{'CAGR':>8}{'MDD':>8}{'Sharpe':>8}{'Trades':>8}{'Win%':>7}")
print('-'*96)
for i,(nm,tot,cagr,mdd,sh,ntr,win) in enumerate(rows_out,1):
    print(f"{i:<3}{nm:<44}{tot*100:>9.1f}%{cagr*100:>7.1f}%{mdd*100:>7.1f}%{sh:>8.2f}{ntr:>8}{win*100:>6.1f}%")
