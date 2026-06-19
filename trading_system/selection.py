"""종목선정팀: 전략 신호(국면 게이트)로 후보 필터 → GBM 예측수익으로 재랭킹(없으면 손코딩 점수)."""
from dataclasses import dataclass
import data as D
try:
    import gbm_model as G
except Exception:
    G = None

@dataclass
class Candidate:
    code: str; name: str; entry: float; stop: float; target: float; score: float; reason: str
    gbm: float = None   # GBM 예측 10일수익(있으면 랭킹 기준)

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

def pick(spec, date, universe=None, max_cands=None):
    universe = universe or D.universe()
    model = G.active_model() if G is not None else None   # 국면 게이트 안에서 재랭킹용
    out = []
    for u in universe:
        p = D.prices(u['code'])
        if not p: continue
        dts = [d for d, _ in p]; C = [c for _, c in p]
        i = _i(dts, date)
        if i is None or i < 60: continue
        c = None
        if spec.signal == "meanrev_confluence": c = _meanrev(spec, C, i, u['code'], u['name'])
        elif spec.signal == "momentum_overnight": c = _momentum(spec, C, i, u['code'], u['name'])
        elif spec.signal == "defensive": c = _defensive(spec, C, i, u['code'], u['name'])
        if c:
            if model is not None:
                g = G.predict_at(model, C, i)
                if g is not None:
                    c.gbm = g; c.reason += f" | GBM {g*100:+.1f}%"
            out.append(c)
    # GBM 예측이 있으면 그걸로 랭킹, 없으면 손코딩 score
    use_gbm = model is not None and any(x.gbm is not None for x in out)
    out.sort(key=lambda x: -(x.gbm if (use_gbm and x.gbm is not None) else x.score))
    return out[:(max_cands or spec.sizing.get('slots', 15))]

def _meanrev(spec, C, i, code, name):
    p = spec.params; sma20 = D.sma(C, p['bb_n'], i)
    if sma20 is None: return None
    w = C[i-p['bb_n']+1:i+1]; sd = (sum((x-sma20)**2 for x in w)/p['bb_n'])**0.5
    lower = sma20 - p['bb_k']*sd; rsi = _rsi(C, p['rsi_n'], i); ma25 = D.sma(C, p['dev_ma'], i)
    if rsi is None or ma25 is None: return None
    dev = C[i]/ma25 - 1
    if C[i] < lower and rsi < p['rsi_thr'] and p['dev_lo'] <= dev <= p['dev_hi']:
        return Candidate(code, name, C[i], C[i]*(1+p['stop']), sma20,
                         round((p['rsi_thr']-rsi) + (-dev)*100, 1),
                         f"RSI{rsi:.0f}, 하단이탈, 이격{dev*100:.0f}%")
    return None

def _momentum(spec, C, i, code, name):
    N = spec.params['lookback_high']
    if i < N: return None
    if C[i] > max(C[i-N:i]):
        ret20 = C[i]/C[i-20]-1 if i >= 20 else 0
        return Candidate(code, name, C[i], C[i]*0.92, C[i]*1.1, round(ret20*100, 1),
                         f"52주 신고가, 20일 모멘텀 {ret20*100:+.0f}%")
    return None

def _defensive(spec, C, i, code, name):
    p = spec.params; ma25 = D.sma(C, p['dev_ma'], i)
    if ma25 is None: return None
    dev = C[i]/ma25 - 1
    if p['dev_lo'] <= dev <= p['dev_hi']:
        return Candidate(code, name, C[i], C[i]*(1+p['stop']), ma25, round(-dev*100, 1),
                         f"극단 과매도 이격{dev*100:.0f}% (방어적 단기반등)")
    return None
