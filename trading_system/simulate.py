"""Phase 3: 전체 멀티-팀 시스템 워크포워드 모의투자(paper) 시뮬레이션.

매 REBAL 거래일마다 [국면판단→전략결정→종목선정→QC] 파이프라인을 돌려
QC 승인 비중으로 포트폴리오를 구성하고, 다음 리밸런싱까지 보유하며 일별 손익을 추적.
외부 API 불필요(캐시 데이터). KOSPI200 단순보유와 비교 + 국면별 기여 분석.

사용: python3 simulate.py [start_date] [end_date]
"""
import sys, math, json
import data as D, regime as R, strategy as S, selection as SEL, qc as QC

REBAL = 5          # 주간(5거래일) 리밸런싱
COST = 0.002       # 매매 회전 비용(편도 근사)

def stats(curve_vals, rets):
    n = len(curve_vals); yrs = n/252
    total = curve_vals[-1]-1; cagr = curve_vals[-1]**(1/yrs)-1 if yrs > 0 else 0
    peak = -1; mdd = 0
    for v in curve_vals:
        peak = max(peak, v); mdd = min(mdd, v/peak-1)
    m = sum(rets)/len(rets); sd = (sum((x-m)**2 for x in rets)/len(rets))**0.5
    sh = m/sd*math.sqrt(252) if sd > 0 else 0
    return total, cagr, mdd, sh

def run(start=None, end=None):
    idx = D.prices('^KS200'); idates = [d for d, _ in idx]; iclose = {d: c for d, c in idx}
    series = {}
    for u in D.universe():
        p = D.prices(u['code'])
        if p: series[u['code']] = {d: c for d, c in p}

    s0 = 252
    dates = idates[s0:]
    if start: dates = [d for d in dates if d >= start]
    if end: dates = [d for d in dates if d <= end]

    weights = {}; eq = 1.0; curve = []; rets = []; rlog = []
    for k, date in enumerate(dates):
        r = 0.0
        if k > 0:
            yday = dates[k-1]
            for code, w in weights.items():
                s = series.get(code)
                if s and date in s and yday in s and s[yday] > 0:
                    r += w*(s[date]/s[yday]-1)
        if k % REBAL == 0:
            view = R.assess(date)                       # 시뮬레이션은 결정론 코어(LLM 생략)
            spec = S.choose(view)
            cands = SEL.pick(spec, date)
            qcr = QC.validate(spec, cands, view, asof=date, run_backtest=False)
            new = {o['code']: o['weight'] for o in qcr.approved_orders}
            allc = set(new) | set(weights)
            turnover = sum(abs(new.get(c, 0)-weights.get(c, 0)) for c in allc)
            r -= turnover*COST
            weights = new
            rlog.append((date, view.regime.value, view.phase, len(new), sum(new.values())))
        eq *= (1+r); rets.append(r); curve.append((date, eq))

    cv = [v for _, v in curve]
    bench_dates = [d for d, _ in curve if d in iclose]
    base = iclose[bench_dates[0]]; bench = [iclose[d]/base for d in bench_dates]
    brets = [bench[i]/bench[i-1]-1 for i in range(1, len(bench))]

    st = stats(cv, rets); bs = stats(bench, brets)
    print(f"SYSTEM PAPER SIM | {dates[0]} ~ {dates[-1]} ({len(dates)}일, 주간 리밸런싱, 비용 {COST*100:.1f}%)")
    print(f"{'':<14}{'SYSTEM':>14}{'KOSPI200 B&H':>16}")
    print('-'*46)
    print(f"{'누적수익':<14}{st[0]*100:>13.1f}%{bs[0]*100:>15.1f}%")
    print(f"{'CAGR':<14}{st[1]*100:>13.1f}%{bs[1]*100:>15.1f}%")
    print(f"{'MDD':<14}{st[2]*100:>13.1f}%{bs[2]*100:>15.1f}%")
    print(f"{'Sharpe':<14}{st[3]:>14.2f}{bs[3]:>16.2f}")
    # 국면 분포
    from collections import Counter
    cnt = Counter(f"{rg}/{ph}" for _, rg, ph, _, _ in rlog)
    print("\n[리밸런싱 국면 분포]")
    for k_, v in cnt.most_common():
        print(f"   {k_:<28} {v}회")
    avg_inv = sum(inv for *_, inv in rlog)/len(rlog)
    print(f"평균 투자비중: {avg_inv*100:.0f}% (나머지 현금)")
    json.dump({'dates': [d for d, _ in curve], 'system': cv, 'bench_dates': bench_dates,
               'bench': bench, 'rlog': rlog}, open('/tmp/sim_result.json', 'w'))
    return st, bs

if __name__ == '__main__':
    a = sys.argv[1] if len(sys.argv) > 1 else None
    b = sys.argv[2] if len(sys.argv) > 2 else None
    run(a, b)
