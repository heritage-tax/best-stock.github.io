"""전략결정팀: 국면 → 검증된 전략 스펙. phase 대응(분산=방어, 저신뢰=노출축소)."""
from dataclasses import dataclass
import copy
from regime import Regime

@dataclass
class StrategySpec:
    name: str; signal: str; params: dict; sizing: dict; note: str = ""

PLAYBOOK = {
    Regime.SIDEWAYS: StrategySpec(
        "Confluence 과매도 역추세 스윙", "meanrev_confluence",
        dict(bb_n=20, bb_k=2.0, rsi_n=14, rsi_thr=30, dev_ma=25, dev_lo=-0.30, dev_hi=-0.08,
             exit_to="sma20", stop=-0.10, maxhold=15),
        dict(slots=15, weight="equal", leverage=1.0, cash_buffer=True),
        "박스권=역추세 무대. 극단 과매도+스윙+손절."),
    Regime.BULL: StrategySpec(
        "모멘텀 오버나잇 (급등주/52주 신고가)", "momentum_overnight",
        dict(lookback_high=252, gainers_top=20, hold="overnight", stop=-0.08, maxhold=15),
        dict(slots=20, weight="equal", leverage=1.0),
        "오버나잇=모멘텀. 종가매수→익일시가매도."),
    Regime.BEAR: StrategySpec(
        "방어 (현금 우선 + 극단 과매도 단기반등)", "defensive",
        dict(dev_ma=25, dev_lo=-0.40, dev_hi=-0.15, stop=-0.06, maxhold=5, max_invested=0.3),
        dict(slots=8, weight="equal", leverage=1.0, cash_buffer=True),
        "추세하락=칼날 주의. 현금↑, 극단 패닉만 빠른 반등."),
}

def choose(view):
    spec = copy.deepcopy(PLAYBOOK[view.regime])
    if view.regime == Regime.BULL and "분산" in (view.phase or ""):
        spec.name = "모멘텀(후기강세 방어 모드)"
        spec.sizing = dict(slots=10, weight="equal", leverage=1.0, cash_buffer=True)
        spec.params = dict(spec.params, trail_stop=-0.05)
        spec.note = "후기강세/분산 — 추격 축소·현금 확보·타이트 익절."
    if view.confidence < 0.3:
        spec.sizing = dict(spec.sizing, slots=max(5, spec.sizing.get('slots', 10)//2))
        spec.note += " | 신뢰도 낮음→노출 축소."
    return spec
