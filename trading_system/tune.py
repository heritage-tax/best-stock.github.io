"""시스템 튜닝·분석: (1) 국면별 수익 기여 분해, (2) 리밸런싱 주기·투자노출 스윕.
python3 tune.py"""
import math
import data as D, regime as R, strategy as S, selection as SEL, qc as QC

COST = 0.002

def sim(rebal=5, exposure=1.0, start='2024-06-13', end=None):
    idx = D.prices('^KS200'); idates = [d for d, _ in idx]; iclose = {d: c for d, c in idx}
    series = {u['code']: {d: c for d, c in (D.prices(u['code']) or [])} for u in D.universe()}
    dates = [d for d in idates[252:] if d >= start and (not end or d <= end)]
    weights = {}; eq = 1.0; rets = []; cur = []
    contrib = {}; days = {}; cur_regime = "?"
    for k, date in enumerate(dates):
        r = 0.0
        if k > 0:
            yday = dates[k-1]
            for code, w in weights.items():
                s = series.get(code)
                if s and date in s and yday in s and s[yday] > 0:
                    r += w*(s[date]/s[yday]-1)
        if k % rebal == 0:
            view = R.assess(date); spec = S.choose(view)
            cands = SEL.pick(spec, date)
            qcr = QC.validate(spec, cands, view, asof=date, run_backtest=False)
            new = {o['code']: o['weight']*exposure for o in qcr.approved_orders}
            tot = sum(new.values())
            if tot > 1.0:  # gross 노출 100% 한도
                new = {c: w/tot for c, w in new.items()}
            allc = set(new) | set(weights)
            r -= sum(abs(new.get(c, 0)-weights.get(c, 0)) for c in allc)*COST
            weights = new; cur_regime = view.regime.value
        contrib[cur_regime] = contrib.get(cur_regime, 0.0) + r
        days[cur_regime] = days.get(cur_regime, 0) + 1
        eq *= (1+r); rets.append(r); cur.append(eq)
    yrs = len(cur)/252; total = cur[-1]-1; cagr = cur[-1]**(1/yrs)-1
    peak = -1; mdd = 0
    for v in cur:
        peak = max(peak, v); mdd = min(mdd, v/peak-1)
    m = sum(rets)/len(rets); sd = (sum((x-m)**2 for x in rets)/len(rets))**0.5
    sh = m/sd*math.sqrt(252) if sd > 0 else 0
    return dict(total=total, cagr=cagr, mdd=mdd, sharpe=sh, contrib=contrib, days=days)

# (1) 기준 시스템 국면별 기여 분해
base = sim(5, 1.0)
print("=== (1) 국면별 수익 기여 분해 (기준: 주간 리밸런싱, 노출 1.0) ===")
print(f"{'국면':<10}{'기여(누적합)':>14}{'일수':>8}")
for rg, c in sorted(base['contrib'].items(), key=lambda x: -x[1]):
    print(f"{rg:<10}{c*100:>13.1f}%{base['days'][rg]:>8}")
print(f"전체: total {base['total']*100:.1f}% CAGR {base['cagr']*100:.1f}% MDD {base['mdd']*100:.1f}% Sharpe {base['sharpe']:.2f}\n")

# (2) 리밸런싱 주기 × 투자노출 스윕
print("=== (2) 파라미터 스윕 (Total% / CAGR% / MDD% / Sharpe) ===")
print('rebal\\expo  ' + ''.join(f'{e:>16}x' for e in [1.0, 1.5, 2.0]))
for rb in [5, 10, 20]:
    row = f"{rb:>3}일     "
    for ex in [1.0, 1.5, 2.0]:
        s = sim(rb, ex)
        row += f"{s['total']*100:>5.0f}/{s['cagr']*100:>3.0f}/{s['mdd']*100:>4.0f}/{s['sharpe']:>4.2f} "
    print(row)
