"""국면판단팀: 산업·경제·미국시장·변동성 종합 → 강세/횡보/하락 + 세분화(phase).
하이브리드: 결정론 7팩터 투표 + LLM 종합층(claude-opus-4-8, graceful fallback)."""
from dataclasses import dataclass, field
from enum import Enum
import os, json
import data as D

class Regime(Enum):
    BULL = "강세장"; SIDEWAYS = "횡보장"; BEAR = "하락장"

@dataclass
class RegimeView:
    regime: Regime
    phase: str
    score: int
    confidence: float
    factors: dict = field(default_factory=dict)
    rationale: str = ""
    source: str = "deterministic"

def _idx(dts, date):
    cand = [k for k, d in enumerate(dts) if d <= date]
    return cand[-1] if cand else None

def assess(date, kospi='^KS200', sp='^GSPC', vix='^VIX'):
    ks = D.prices(kospi)
    if not ks:
        return RegimeView(Regime.SIDEWAYS, "박스권", 0, 0.0, rationale="지수 데이터 없음")
    dts = [d for d, _ in ks]; C = [c for _, c in ks]
    i = _idx(dts, date)
    if i is None or i < 200:
        return RegimeView(Regime.SIDEWAYS, "박스권", 0, 0.0, rationale="데이터 부족")
    f = {}
    ma200 = D.sma(C, 200, i)
    f['idx>200MA'] = 1 if C[i] > ma200 else -1
    ma200p = D.sma(C, 200, i-40)
    f['200MA_slope'] = 1 if (ma200p and ma200 > ma200p) else -1
    hi = max(C[i-251:i+1]); dd = C[i]/hi - 1
    f['drawdown'] = 1 if dd > -0.05 else (-1 if dd < -0.20 else 0)
    vol = D.realized_vol(C, 20, i) or 0
    f['volatility'] = 1 if vol < 0.15 else (-1 if vol > 0.30 else 0)
    above = tot = 0
    for u in D.universe():
        p = D.prices(u['code'])
        if not p: continue
        pd = [d for d, _ in p]; pc = [c for _, c in p]
        j = _idx(pd, date)
        if j is None or j < 200: continue
        m = D.sma(pc, 200, j)
        if m: tot += 1; above += (1 if pc[j] > m else 0)
    breadth = (above/tot) if tot else 0.5
    f['breadth'] = 1 if breadth > 0.60 else (-1 if breadth < 0.40 else 0)
    f['_breadth_pct'] = round(breadth*100, 1)
    sp_p = D.prices(sp)
    if sp_p:
        sd = [d for d, _ in sp_p]; sc = [c for _, c in sp_p]; k = _idx(sd, date)
        if k and k >= 200:
            m = D.sma(sc, 200, k); f['US_S&P>200MA'] = 1 if sc[k] > m else -1
    vx = D.prices(vix)
    if vx:
        vd = [d for d, _ in vx]; vc = [c for _, c in vx]; k = _idx(vd, date)
        if k:
            f['VIX'] = 1 if vc[k] < 20 else (-1 if vc[k] > 28 else 0)
            f['_VIX_level'] = round(vc[k], 1)

    votes = [v for kk, v in f.items() if not kk.startswith('_')]
    score = sum(votes); maxs = len(votes)
    if f.get('drawdown') == -1 and f.get('volatility') == -1:
        regime = Regime.BEAR
    elif score >= 3:
        regime = Regime.BULL
    elif score <= -3:
        regime = Regime.BEAR
    else:
        regime = Regime.SIDEWAYS
    if regime == Regime.BULL:
        weak = (breadth < 0.55) or (f.get('volatility') == -1) or (dd < -0.07)
        phase = "후기강세/분산(distribution)" if weak else "강세 본류"
    elif regime == Regime.BEAR:
        phase = "패닉/투매" if dd < -0.30 else "초기하락"
    else:
        phase = "박스권"
    conf = abs(score)/maxs if maxs else 0
    rat = (f"score={score}/{maxs}, breadth={f.get('_breadth_pct')}%, "
           f"VIX={f.get('_VIX_level')}, dd={dd*100:.1f}%, vol={vol*100:.0f}%")
    return RegimeView(regime, phase, score, round(conf, 2), f, rat)

_SCHEMA = {"type": "object", "properties": {
    "regime": {"type": "string", "enum": ["강세장", "횡보장", "하락장"]},
    "phase": {"type": "string"}, "confidence": {"type": "number"}, "rationale": {"type": "string"}},
    "required": ["regime", "phase", "confidence", "rationale"], "additionalProperties": False}

def assess_llm(view, news_context="", model="claude-opus-4-8"):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        view.rationale += " | (LLM 미적용: ANTHROPIC_API_KEY 없음)"; return view
    try:
        import anthropic
        client = anthropic.Anthropic()
        fac = {k: v for k, v in view.factors.items() if not k.startswith('_')}
        prompt = ("당신은 한국 주식시장 국면 판단 보조자입니다. 정량 지표와 뉴스 맥락을 종합해 "
                  "국면(강세장/횡보장/하락장)·세부단계·신뢰도(0~1)·근거를 JSON으로 답하세요. "
                  "정량을 존중하되 매크로/정책이 분명히 다를 때만 조정.\n\n"
                  f"[정량] {view.regime.value}/{view.phase} (conf {view.confidence})\n"
                  f"[7팩터] {fac}\n[보조] {view.rationale}\n[뉴스/매크로] {news_context or '(없음)'}\n")
        resp = client.messages.create(model=model, max_tokens=1024,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": prompt}])
        out = json.loads(next(b.text for b in resp.content if b.type == "text"))
        for r in Regime:
            if r.value == out["regime"]: view.regime = r; break
        view.phase = out.get("phase", view.phase)
        view.confidence = round(float(out.get("confidence", view.confidence)), 2)
        view.rationale += f" | LLM: {out.get('rationale','')}"; view.source = "hybrid(LLM)"
    except Exception as e:
        view.rationale += f" | (LLM 보정 생략: {type(e).__name__})"
    return view
