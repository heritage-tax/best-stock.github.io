"""실시간 모니터링 → 텔레그램 매수/매도 신호 (맥미니 상주 데몬).
장중(09:00~15:30 KST) MONITOR_INTERVAL초마다:
  1) 국면→전략 결정(전일 종가 기준, 느리게 변함)
  2) KIS 실시간가를 '오늘 종가'로 주입해 전략 신호 재계산 + GBM 재랭킹
  3) 새 매수신호(상위 슬롯 신규 진입) → 텔레그램
  4) 보유종목(KIS 잔고)이 평균선 복귀(익절)/손절 도달 → 텔레그램 매도신호
KIS 미연결 시 마지막 종가로 폴백(개발/장외 테스트). 신호는 당일 1회만(중복방지).

사용:  python3 monitor.py          # 상주 루프
       python3 monitor.py --once  # 1회 점검(테스트)
환경변수: TELEGRAM_*, KIS_*, MONITOR_INTERVAL(기본300), STOP_PCT(기본-0.10), WATCH_MAX(기본200)
"""
import os, sys, time, datetime
import data as D, regime as R, strategy as S, selection as SEL, notify_telegram as TG
try: import gbm_model as G
except Exception: G = None
try: import data_kis as KIS
except Exception: KIS = None

INTERVAL = int(os.environ.get('MONITOR_INTERVAL', '300'))
STOP = float(os.environ.get('STOP_PCT', '-0.10'))
WATCH_MAX = int(os.environ.get('WATCH_MAX', '200'))
KIS_ON = bool(KIS and os.environ.get('KIS_APP_KEY'))

def live_price(code, fallback):
    if KIS_ON:
        try:
            px = KIS.current_price(code); time.sleep(0.03)  # KIS 레이트리밋 배려
            return px
        except Exception:
            return fallback
    return fallback

def c_live(code):
    """과거 종가 + 실시간가(오늘)로 시리즈 구성 → (C, last_index)."""
    p = D.prices(code)
    if not p or len(p) < 70: return None, None
    dts = [d for d, _ in p]; C = [c for _, c in p]
    lp = live_price(code, C[-1])
    today = datetime.date.today().isoformat()
    C = (C[:-1] + [lp]) if dts[-1] == today else (C + [lp])
    return C, len(C)-1

def held_positions():
    if KIS_ON:
        try: return {x['code']: x for x in KIS.balance()}
        except Exception as e: print(f"[monitor] 잔고조회 오류: {e}")
    return {}

def market_open(now=None):
    now = now or datetime.datetime.now()
    if now.weekday() >= 5: return False
    t = now.hour*60 + now.minute
    return 540 <= t <= 930   # 09:00~15:30

def cycle(state):
    today = datetime.date.today().isoformat()
    if state.get('day') != today:
        state.update(day=today, buy=set(), sell=set())
    view = R.assess(D.prices('^KS200')[-1][0])
    spec = S.choose(view)
    model = G.active_model() if G else None
    sigfn = {'meanrev_confluence': SEL._meanrev, 'momentum_overnight': SEL._momentum,
             'defensive': SEL._defensive}.get(spec.signal)

    # --- 매수 후보 스캔 ---
    cands = []
    for u in D.universe()[:WATCH_MAX]:
        C, i = c_live(u['code'])
        if C is None or not sigfn: continue
        c = sigfn(spec, C, i, u['code'], u['name'])
        if c:
            if model is not None:
                g = G.predict_at(model, C, i)
                if g is not None: c.gbm = g
            cands.append(c)
    use_gbm = model is not None and any(x.gbm is not None for x in cands)
    cands.sort(key=lambda x: -(x.gbm if (use_gbm and x.gbm is not None) else x.score))
    slots = spec.sizing.get('slots', 15)
    new_buys = [c for c in cands[:slots] if c.code not in state['buy']]
    for c in new_buys: state['buy'].add(c.code)
    if new_buys:
        TG.send(f"🟢 *매수신호* ({view.regime.value}·{view.phase}) {today}\n" + "\n".join(
            f"• *{c.name}*({c.code}) @ {c.entry:,.0f} | 손절 {c.stop:,.0f} 목표 {c.target:,.0f}"
            + (f" | GBM {c.gbm*100:+.1f}%" if c.gbm is not None else "") for c in new_buys)
            + "\n⚠️ 참고용. 직접 판단·실행.")

    # --- 매도(보유종목 청산) 신호 ---
    new_sells = []
    for code, pos in held_positions().items():
        C, i = c_live(code)
        if C is None: continue
        sma20 = D.sma(C, 20, i); px = C[i]; avg = pos.get('avg', 0)
        if sma20 and px >= sma20: reason = f"평균선 복귀(익절) @ {px:,.0f}"
        elif avg and px <= avg*(1+STOP): reason = f"손절 {STOP*100:.0f}% @ {px:,.0f} (평단 {avg:,.0f})"
        else: continue
        if code not in state['sell']:
            state['sell'].add(code); new_sells.append((pos.get('name', code), code, reason, pos.get('pl_pct')))
    if new_sells:
        TG.send(f"🔴 *매도신호* {today}\n" + "\n".join(
            f"• *{n}*({c}) {r}" + (f" (평가손익 {pl:+.1f}%)" if pl is not None else "")
            for n, c, r, pl in new_sells) + "\n⚠️ 참고용. 직접 판단·실행.")
    return len(new_buys), len(new_sells)

def main():
    once = '--once' in sys.argv
    state = {}
    print(f"[monitor] 시작 interval={INTERVAL}s KIS={'ON' if KIS_ON else 'OFF(종가폴백)'} GBM={'ON' if (G and G.active_model()) else 'OFF'}")
    while True:
        try:
            if once or market_open():
                b, s = cycle(state)
                print(f"[monitor] {datetime.datetime.now():%m-%d %H:%M} 매수 {b} 매도 {s}")
            if once: break
        except Exception as e:
            print(f"[monitor] cycle 오류: {type(e).__name__} {e}")
        if once: break
        time.sleep(INTERVAL)

if __name__ == '__main__':
    main()
