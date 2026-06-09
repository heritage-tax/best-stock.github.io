import json, os, csv, math
from datetime import datetime
import collections

YH='/tmp/yh5'
K=0.5
OR_BARS=3          # 09:00,09:05,09:10 -> first 15 min (~"14 min")

def load_days(sym):
    """return dict: date -> list of (hhmm, o,h,l,c) for the regular session, sorted."""
    fp=f'{YH}/{sym}.json'
    if not os.path.exists(fp): return None
    j=json.load(open(fp))
    res=j['chart']['result'][0]
    ts=res['timestamp']; q=res['indicators']['quote'][0]
    gmt=res['meta'].get('gmtoffset',32400)
    days=collections.defaultdict(list)
    for i,t in enumerate(ts):
        o,h,l,c=q['open'][i],q['high'][i],q['low'][i],q['close'][i]
        if None in (o,h,l,c): continue
        lt=datetime.utcfromtimestamp(t+gmt)
        hhmm=lt.hour*60+lt.minute
        if hhmm<540 or hhmm>930: continue   # 09:00(540) .. 15:30(930)
        days[lt.strftime('%Y-%m-%d')].append((hhmm,o,h,l,c))
    for d in days: days[d].sort()
    return days

syms=[]
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())

# Opening-Range Breakout (Larry Williams intraday, K=0.5):
#  open_ref = open of first bar
#  R14 = max(high)-min(low) over first OR_BARS bars (09:00-09:14)
#  target = open_ref + K*R14
#  from bar OR_BARS onward: first bar with high>=target -> enter at max(target, bar_open)
#  exit at last bar close (same-day liquidation)
#  gross trade ret = exit/entry - 1
daily=collections.defaultdict(list)   # date -> [trade rets]
o2c=collections.defaultdict(list)     # date -> [open->close rets] (intraday B&H baseline)
loaded=0
for s in syms:
    if s=='^KS200': continue
    days=load_days(s)
    if not days: continue
    loaded+=1
    for d,bars in days.items():
        if len(bars)<OR_BARS+2: continue
        oref=bars[0][1]
        orh=max(b[2] for b in bars[:OR_BARS]); orl=min(b[3] for b in bars[:OR_BARS])
        R=orh-orl
        if R<=0 or oref<=0: continue
        target=oref+K*R
        last_close=bars[-1][4]
        o2c[d].append(last_close/bars[0][1]-1)
        entry=None
        for b in bars[OR_BARS:]:
            if b[2]>=target:
                entry=max(target,b[1])   # fill at target, or bar open if gapped above
                break
        if entry and entry>0:
            daily[d].append(last_close/entry-1)

dates=sorted(daily.keys())

def run(cost):
    eq=1.0;cur=[];rets=[]
    for d in dates:
        trs=daily[d]
        r=(sum(trs)/len(trs)-cost) if trs else 0.0
        eq*=(1+r);rets.append(r);cur.append(eq)
    return cur,rets

def stats(cv,rets):
    yrs=len(cv)/252
    total=cv[-1]-1; cagr=cv[-1]**(1/yrs)-1 if yrs>0 else 0
    peak=-1;mdd=0
    for v in cv: peak=max(peak,v);mdd=min(mdd,v/peak-1)
    m=sum(rets)/len(rets); sd=(sum((x-m)**2 for x in rets)/len(rets))**0.5
    sh=m/sd*math.sqrt(252) if sd>0 else 0
    return total,cagr,mdd,sh,m

alltr=[x for v in daily.values() for x in v]
wins=sum(1 for x in alltr if x>0)
avg_names=sum(len(daily[d]) for d in dates)/len(dates)

# intraday buy&hold baseline: equal-weight open->close each day across universe
bh=[]
for d in dates:
    arr=o2c[d]; bh.append(sum(arr)/len(arr) if arr else 0)
bh_eq=1.0;bh_cur=[]
for r in bh: bh_eq*=(1+r);bh_cur.append(bh_eq)

print(f"Universe: {loaded} names | days: {len(dates)} ({dates[0]} ~ {dates[-1]})")
print(f"OR window: first {OR_BARS} bars (~15min) | trades={len(alltr)} | avg {avg_names:.0f} entries/day | win {wins/len(alltr)*100:.1f}%")
print(f"Mean gross trade ret: {sum(alltr)/len(alltr)*100:.3f}%")
print()
print(f"{'METRIC':<14}{'Gross':>12}{'Net@0.10%':>12}{'Net@0.20%':>12}{'Net@0.35%':>12}{'IntradayBH':>12}")
print('-'*74)
sc={'Gross':0.0,'Net@0.10%':0.001,'Net@0.20%':0.002,'Net@0.35%':0.0035}
R={k:run(c) for k,c in sc.items()}
S={k:stats(*R[k]) for k in sc}
bh_s=stats(bh_cur,bh)
def row(lbl,f):
    print(f"{lbl:<14}"+"".join(f"{f(S[k]):>12}" for k in sc)+f"{f(bh_s):>12}")
row('Total ret',lambda s:f"{s[0]*100:.1f}%")
row('CAGR',     lambda s:f"{s[1]*100:.1f}%")
row('MDD',      lambda s:f"{s[2]*100:.1f}%")
row('Sharpe',   lambda s:f"{s[3]:.2f}")
row('Avg daily',lambda s:f"{s[4]*100:.3f}%")

json.dump({'dates':dates,'gross':R['Gross'][0],'net20':R['Net@0.20%'][0],
           'net35':R['Net@0.35%'][0],'bh':bh_cur,'loaded':loaded,
           'mean_gross':sum(alltr)/len(alltr),'win':wins/len(alltr),
           'avg_names':avg_names,'ntr':len(alltr)},open('/tmp/intraday_result.json','w'))
