"""(A) 과최적화 검증: Deflated Sharpe Ratio + 워크포워드(아웃오브샘플).
리서치 교훈(Bailey·López de Prado) 적용 — 우리 시스템 성과가 진짜인지, 시행횟수·표본 보정 후에도 유의한지.
python3 overfit_check.py"""
import math
from statistics import NormalDist, mean, pstdev, variance
import data as D, regime as R, strategy as S, selection as SEL, qc as QC

COST = 0.002
idx = D.prices('^KS200'); idates = [d for d, _ in idx]; iclose = dict(idx)
series = {u['code']: dict(D.prices(u['code']) or []) for u in D.universe()}
START = '2024-06-13'
dates = [d for d in idates[252:] if d >= START]
N = len(dates)

# 국면·선정·QC는 (rb,ex)와 무관 → 날짜별 1회 계산 후 캐시 재사용
_oc = {}
def get_orders(date):
    if date not in _oc:
        view = R.assess(date); spec = S.choose(view)
        cands = SEL.pick(spec, date)
        qcr = QC.validate(spec, cands, view, asof=date, run_backtest=False)
        _oc[date] = {o['code']: o['weight'] for o in qcr.approved_orders}
    return _oc[date]

def sim_rets(rebal, exposure, lo=0, hi=None):
    hi = hi if hi is not None else N
    weights = {}; rets = []
    for k in range(lo, hi):
        date = dates[k]; r = 0.0
        if k > lo:
            y = dates[k-1]
            for c, w in weights.items():
                s = series.get(c)
                if s and date in s and y in s and s[y] > 0: r += w*(s[date]/s[y]-1)
        if (k-lo) % rebal == 0:
            new = {c: w*exposure for c, w in get_orders(date).items()}
            tot = sum(new.values())
            if tot > 1.0: new = {c: w/tot for c, w in new.items()}
            allc = set(new) | set(weights)
            r -= sum(abs(new.get(c, 0)-weights.get(c, 0)) for c in allc)*COST
            weights = new
        rets.append(r)
    return rets

def ann_sharpe(rets):
    sd = pstdev(rets)
    return (mean(rets)/sd*math.sqrt(252)) if sd > 0 else 0.0
def total(rets):
    e = 1.0
    for r in rets: e *= (1+r)
    return e-1
def kospi(lo, hi):
    ds = [dates[k] for k in range(lo, hi) if dates[k] in iclose]
    return iclose[ds[-1]]/iclose[ds[0]]-1

# ===== 1) Deflated Sharpe Ratio =====
trials = [(rb, ex) for rb in [5, 10, 20] for ex in [1.0, 1.5, 2.0]]
trial_rets = {t: sim_rets(*t) for t in trials}
daily_sr = {t: (mean(r)/pstdev(r) if pstdev(r) > 0 else 0) for t, r in trial_rets.items()}  # 일간 SR
chosen = (5, 1.5)
rets = trial_rets[chosen]; SR = daily_sr[chosen]; T = len(rets)
V = variance(list(daily_sr.values()))           # 시행 간 SR 분산
n_trials = len(trials)
g = 0.5772156649; nd = NormalDist()
SR0 = math.sqrt(V)*((1-g)*nd.inv_cdf(1-1/n_trials) + g*nd.inv_cdf(1-1/(n_trials*math.e)))
m = mean(rets); sd = pstdev(rets)
skew = sum((x-m)**3 for x in rets)/len(rets)/sd**3
kurt = sum((x-m)**4 for x in rets)/len(rets)/sd**4   # 비초과(정규=3)
DSR = nd.cdf((SR-SR0)*math.sqrt(T-1)/math.sqrt(1 - skew*SR + ((kurt-1)/4)*SR**2))

print("="*60)
print("(1) DEFLATED SHARPE RATIO — 시행횟수·표본 보정")
print(f"  선택 config: rebal={chosen[0]}일, exposure={chosen[1]}x")
print(f"  관측 연 Sharpe: {ann_sharpe(rets):.2f}  (일간 SR={SR:.4f}, T={T})")
print(f"  시행 횟수 N={n_trials} (rebal×exposure 스윕)")
print(f"  벤치 SR0(우연 최대치): 일간 {SR0:.4f} = 연 {SR0*math.sqrt(252):.2f}")
print(f"  skew={skew:.2f}, kurtosis={kurt:.2f}")
print(f"  >>> Deflated Sharpe = {DSR:.3f}  ({'유의(>0.95)' if DSR>0.95 else '유의하지 않음(<0.95) → 과최적화 의심'})")

# ===== 2) 워크포워드 (아웃오브샘플) =====
mid = N//2
print("\n" + "="*60)
print("(2) 워크포워드 — IS에서 최적 파라미터 선택 → OOS 평가")
print(f"  IS(전반) {dates[0]}~{dates[mid-1]} / OOS(후반) {dates[mid]}~{dates[-1]}")
# IS에서 최적 (rb,ex) 선택
is_best = max(trials, key=lambda t: ann_sharpe(sim_rets(*t, 0, mid)))
is_sh = ann_sharpe(sim_rets(*is_best, 0, mid))
oos = sim_rets(*is_best, mid, N)
print(f"  IS 최적 config: rebal={is_best[0]}, exposure={is_best[1]}x  (IS 연Sharpe {is_sh:.2f})")
print(f"  → OOS 적용 결과: 연Sharpe {ann_sharpe(oos):.2f}, 누적 {total(oos)*100:+.1f}%  (KOSPI200 OOS {kospi(mid,N)*100:+.1f}%)")
# 고정 chosen config의 IS vs OOS (안정성)
cis = sim_rets(*chosen, 0, mid); coos = sim_rets(*chosen, mid, N)
print(f"  [참고] 고정 config(5,1.5):  IS 연Sharpe {ann_sharpe(cis):.2f} / 누적 {total(cis)*100:+.1f}%"
      f"  vs  OOS 연Sharpe {ann_sharpe(coos):.2f} / 누적 {total(coos)*100:+.1f}%")
print("="*60)
