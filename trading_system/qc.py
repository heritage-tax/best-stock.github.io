"""QC 검증팀: 리스크·데이터·정합성 + 백테스트 게이트."""
from dataclasses import dataclass, field
import data as D

@dataclass
class QCResult:
    approved: bool
    reasons: list = field(default_factory=list)
    approved_orders: list = field(default_factory=list)
    backtest: dict = field(default_factory=dict)

MAX_WEIGHT_PER_NAME = 0.10
COST = 0.002

def _i(dts, date):
    cand = [k for k, d in enumerate(dts) if d <= date]
    return cand[-1] if cand else None

def _rsi(C, n, i):
    if i <= n: return None
    g = l = 0
    for k in range(i-n+1, i+1):
        ch = C[k]-C[k-1]; g += max(ch, 0); l += max(-ch, 0)
    ag, al = g/n, l/n
    return 100 - 100/(1+ag/al) if al > 0 else 100

def backtest_signal(spec, asof, lookback_days=120, fwd=5):
    rets = []
    for u in D.universe():
        p = D.prices(u['code'])
        if not p or len(p) < 260: continue
        dts = [d for d, _ in p]; C = [c for _, c in p]
        end = _i(dts, asof)
        if end is None: continue
        start = max(25, end - lookback_days)
        for t in range(start, end - fwd):
            if spec.signal == "meanrev_confluence":
                sma = D.sma(C, 20, t); ma25 = D.sma(C, 25, t)
                if not (sma and ma25): continue
                w = C[t-19:t+1]; sd = (sum((x-sma)**2 for x in w)/20)**0.5
                rsi = _rsi(C, 14, t); dev = C[t]/ma25-1
                if C[t] < sma-2*sd and rsi is not None and rsi < 30 and -0.30 <= dev <= -0.08:
                    ex = None
                    for j in range(t+1, t+1+fwd):
                        sj = D.sma(C, 20, j)
                        if sj and C[j] >= sj: ex = C[j]/C[t]-1; break
                    rets.append((ex if ex is not None else C[t+fwd]/C[t]-1) - COST)
            elif spec.signal == "momentum_overnight":
                N = spec.params.get('lookback_high', 252)
                if t < N: continue
                if C[t] > max(C[t-N:t]): rets.append(C[t+fwd]/C[t]-1 - COST)
            elif spec.signal == "defensive":
                ma25 = D.sma(C, 25, t)
                if not ma25: continue
                if -0.40 <= C[t]/ma25-1 <= -0.15: rets.append(C[min(t+5,len(C)-1)]/C[t]-1 - COST)
    if not rets: return {"n": 0, "mean": 0.0, "win": 0.0}
    m = sum(rets)/len(rets); w = sum(1 for x in rets if x > 0)/len(rets)
    return {"n": len(rets), "mean": m, "win": w}

def validate(spec, cands, regime_view, asof=None, run_backtest=True):
    reasons = []; slots = spec.sizing.get('slots', 15)
    weight = min(1.0/slots, MAX_WEIGHT_PER_NAME)
    if not cands: reasons.append("후보 종목 없음 → 현금 보유")
    bt = {}
    if run_backtest and asof and cands:
        bt = backtest_signal(spec, asof)
        if bt["n"] >= 20:
            if bt["mean"] <= 0:
                reasons.append(f"⚠ 최근 신호 기대수익 음(-) ({bt['mean']*100:.2f}%/회, 승률 {bt['win']*100:.0f}%) → 비중 절반·관망")
                weight *= 0.5
            else:
                reasons.append(f"백테스트 게이트 통과: 최근 {bt['n']}건 기대 {bt['mean']*100:+.2f}%/회, 승률 {bt['win']*100:.0f}%")
        else:
            reasons.append(f"백테스트 표본 부족({bt['n']}건) → 비중 보수적"); weight *= 0.7
    if regime_view.regime.name == 'BEAR':
        reasons.append(f"하락장 투자한도 {spec.params.get('max_invested',1.0):.0%} (현금 우선)")
    if regime_view.confidence < 0.3:
        reasons.append(f"국면 신뢰도 낮음({regime_view.confidence}) → 비중 축소")
    bad = [c for c in cands if not (c.entry and c.entry > 0)]
    if bad:
        reasons.append(f"데이터 이상 {len(bad)}개 제외"); cands = [c for c in cands if c not in bad]
    orders = [{'code': c.code, 'name': c.name, 'entry': c.entry, 'stop': c.stop,
               'target': c.target, 'weight': round(weight, 4), 'reason': c.reason} for c in cands]
    return QCResult(len(orders) > 0, reasons, orders, bt)
