import json, os, csv, math
from datetime import datetime
import collections

YH='/tmp/yh5'; K=0.5; OR_BARS=6

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

def trade_day(bars):
    """return (long_ret, short_ret, combo_ret) gross; combo = first band crossed."""
    if len(bars)<OR_BARS+2: return None,None,None
    oref=bars[0][1]
    orh=max(b[2] for b in bars[:OR_BARS]);orl=min(b[3] for b in bars[:OR_BARS])
    R=orh-orl;last=bars[-1][4]
    if R<=0 or oref<=0: return None,None,None
    up=oref+K*R; dn=oref-K*R
    long_ret=short_ret=combo=None
    # long: first bar high>=up
    for b in bars[OR_BARS:]:
        if b[2]>=up:
            e=max(up,b[1]); long_ret=last/e-1; break
    # short: first bar low<=dn
    for b in bars[OR_BARS:]:
        if b[3]<=dn:
            e=min(dn,b[1]); short_ret=(e-last)/e; break
    # combo: whichever crosses first chronologically
    for b in bars[OR_BARS:]:
        hit_up=b[2]>=up; hit_dn=b[3]<=dn
        if hit_up and hit_dn:
            if b[4]>=b[1]: e=max(up,b[1]); combo=last/e-1
            else: e=min(dn,b[1]); combo=(e-last)/e
            break
        if hit_up: e=max(up,b[1]); combo=last/e-1; break
        if hit_dn: e=min(dn,b[1]); combo=(e-last)/e; break
    return long_ret,short_ret,combo

L=collections.defaultdict(list);Sh=collections.defaultdict(list);C=collections.defaultdict(list)
for i in range(1,len(weeks)):
    top=select_top(weeks[i-1]); testw=weeks[i]
    for s in top:
        if s not in data: continue
        for d in wkdays[testw].get(s,[]):
            lr,sr,cr=trade_day(data[s][d])
            if lr is not None: L[d].append(lr)
            if sr is not None: Sh[d].append(sr)
            if cr is not None: C[d].append(cr)

dates=sorted(set(list(L)+list(Sh)+list(C)))
def run(book,cost):
    eq=1.0;cur=[];rets=[]
    for d in dates:
        trs=book.get(d,[]); r=(sum(trs)/len(trs)-cost) if trs else 0.0
        eq*=(1+r);rets.append(r);cur.append(eq)
    return cur,rets
def stats(cv,rets):
    yrs=len(cv)/252;total=cv[-1]-1;cagr=cv[-1]**(1/yrs)-1 if yrs>0 else 0
    peak=-1;mdd=0
    for v in cv: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets);sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    return total,cagr,mdd,(m/sd*math.sqrt(252) if sd>0 else 0),m

def summ(nm,book):
    allt=[x for v in book.values() for x in v];w=sum(1 for x in allt if x>0)
    print(f"\n## {nm}: trades={len(allt)} win={w/len(allt)*100:.1f}% mean_gross/trade={sum(allt)/len(allt)*100:.3f}%")
    print(f"{'':<10}{'Gross':>11}{'Net@0.10%':>11}{'Net@0.20%':>11}{'Net@0.35%':>11}")
    sc={'g':0.0,'n10':0.001,'n20':0.002,'n35':0.0035}
    S={k:stats(*run(book,c)) for k,c in sc.items()}
    for lbl,idx,f in [('Total',0,lambda v:f"{v*100:.1f}%"),('CAGR',1,lambda v:f"{v*100:.1f}%"),
                      ('MDD',2,lambda v:f"{v*100:.1f}%"),('Sharpe',3,lambda v:f"{v:.2f}")]:
        print(f"{lbl:<10}"+"".join(f"{f(S[k][idx]):>11}" for k in sc))
    return run(book,0.0)[0], run(book,0.002)[0]

print(f"WALK-FORWARD + SHORT | weeks={len(weeks)-1} days={len(dates)} ({dates[0]}~{dates[-1]})")
g_l,_=summ('LONG only (upside breakout)',L)
g_s,n_s=summ('SHORT only (downside breakout)',Sh)
g_c,n_c=summ('COMBINED (first band)',C)

idx=load_days('^KS200');idxc={d:bars[-1][4] for d,bars in idx.items()}
bd=[d for d in dates if d in idxc];base=idxc[bd[0]];bench=[idxc[d]/base for d in bd]
json.dump({'dates':dates,'long':g_l,'short':g_s,'short_n20':n_s,'combo':g_c,'combo_n20':n_c,
           'bdates':bd,'bench':bench},open('/tmp/wfs_result.json','w'))
print('\nKOSPI200 over window:',f"{(bench[-1]-1)*100:.1f}%")
