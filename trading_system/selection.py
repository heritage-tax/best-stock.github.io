"""종목선정팀: 전략 신호(국면 게이트)로 후보 필터 → GBM 예측수익으로 재랭킹(없으면 손코딩 점수)."""
from dataclasses import dataclass
import os
import data as D
try:
    import gbm_model as G
except Exception:
    G = None

# GBM 랭킹은 OOS 종목선택력이 없어 기본 OFF. 룰 기반(과매도 깊이 score)으로 랭킹.
# 되살리려면 config.sh 에 USE_GBM_RANK=1.
USE_GBM_RANK = os.environ.get('USE_GBM_RANK', '0') == '1'

@dataclass
class Candidate:
    code: str; name: str; entry: float; stop: float; target: float; score: float; reason: str
    gbm: float = None   # GBM 예측 10일수익(있으면 랭킹 기준)

# 하락장 추천용 1배 인버스 ETF (지수 하락 시 수익). 개인 공매도는 비현실적이라 인버스로 대체.
INVERSE_ETFS = [{'code': '114800.KS', 'name': 'KODEX 인버스'}]

def _inverse(code, name, C, i, stop=-0.08, target=0.15):
    """1배 인버스: 인버스가 20일선 위(=지수 하락추세 진행)일 때만 매수. 익절 시 정점 추격 방지."""
    sma20 = D.sma(C, 20, i)
    if sma20 is None or i < 20:
        return None
    if C[i] > sma20:   # 인버스 상승추세 = 시장 하락추세 살아있음
        mom = C[i] / sma20 - 1
        return Candidate(code, name, C[i], C[i]*(1+stop), C[i]*(1+target),
                         round(mom*100, 1),
                         f"하락장 인버스(-1x) 매수 · 지수↓ 베팅 (20일선 +{mom*100:.0f}%)")
    return None

def _inverse_candidates(date):
    out = []
    for iv in INVERSE_ETFS:
        p = D.prices(iv['code'])
        if not p:
            continue
        dts = [d for d, _ in p]; C = [c for _, c in p]
        i = _i(dts, date)
        if i is None or i < 20:
            continue
        c = _inverse(iv['code'], iv['name'], C, i)
        if c:
            out.append(c)
    return out

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
    model = G.active_model() if (G is not None and USE_GBM_RANK) else None   # 기본 OFF → score 랭킹
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
                v = D.volumes(u['code']); V = list(v) if v else None
                g = G.predict_at(model, C, i, V)
                if g is not None:
                    c.gbm = g; c.reason += f" | GBM {g*100:+.1f}%"
            out.append(c)
    # GBM 예측이 있으면 그걸로 랭킹, 없으면 손코딩 score
    use_gbm = model is not None and any(x.gbm is not None for x in out)
    out.sort(key=lambda x: -(x.gbm if (use_gbm and x.gbm is not None) else x.score))
    # 하락장: 인버스 ETF를 최우선 후보로 (GBM은 개별주 학습이라 인버스엔 미적용)
    if spec.signal == "defensive":
        out = _inverse_candidates(date) + out
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
