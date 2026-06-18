"""일일 실행 엔트리포인트 (맥미니 launchd/cron에서 매일 호출).
 1) 데이터 갱신(선택)  2) 국면→전략→선정→QC  3) 권고 포맷  4) 텔레그램 발송

사용:
  python3 daily.py            # 최신 데이터 기준 권고 → 텔레그램
  python3 daily.py --no-fetch # 데이터 갱신 생략(이미 최신일 때)
환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, (선택) ANTHROPIC_API_KEY(LLM 국면보정)
"""
import sys, os, subprocess, datetime
import data as D, regime as R, strategy as S, selection as SEL, qc as QC
import notify_telegram as TG

EXPOSURE = float(os.environ.get("EXPOSURE", "1.5"))   # 튜닝 결론: 1.5x 권장

def refresh_data():
    """일봉 데이터 갱신(Yahoo). KIS는 잔고·시세 보조용(data_kis.py)이며 가격 캐시는 Yahoo 사용."""
    fetch = os.environ.get("FETCH_SCRIPT", "")
    if fetch and os.path.exists(fetch):
        try:
            subprocess.run([sys.executable, fetch], check=True, timeout=900)
        except Exception as e:
            print(f"[daily] 데이터 갱신 경고: {e} (기존 캐시로 진행)")

def format_msg(date, view, spec, qc):
    lines = [f"📊 *KOSPI 트레이딩 권고* ({date})",
             f"━━━━━━━━━━━━━━━━━━",
             f"🧭 국면: *{view.regime.value} · {view.phase}*  (신뢰도 {view.confidence})",
             f"🎯 전략: {spec.name}",
             f"💰 노출: {EXPOSURE:.1f}x"]
    if not qc.approved or not qc.approved_orders:
        lines.append("\n⚪️ *오늘 신규 매수 권고 없음* (현금 보유)")
    else:
        cap = float(os.environ.get("CAPITAL", "10000000"))  # 기본 1천만원
        lines.append(f"\n🟢 *매수 권고* ({len(qc.approved_orders)}종목)")
        for o in qc.approved_orders:
            w = min(o['weight']*EXPOSURE, 0.10)
            amt = cap*w
            lines.append(f"• *{o['name']}* ({o['code']})\n"
                         f"   진입 {o['entry']:,.0f} / 손절 {o['stop']:,.0f} / 목표 {o['target']:,.0f}\n"
                         f"   비중 {w*100:.1f}% (≈{amt:,.0f}원) | {o['reason']}")
    if qc.reasons:
        lines.append("\n🔎 QC: " + " / ".join(qc.reasons[:3]))
    lines.append("\n⚠️ 참고용. 매수/매도는 직접 판단·실행하세요.")
    return "\n".join(lines)

def main():
    if "--no-fetch" not in sys.argv:
        refresh_data()
    ks = D.prices('^KS200')
    if not ks:
        TG.send("⚠️ 데이터 없음 — 권고 생성 실패. 데이터 갱신 확인 필요.")
        return
    date = ks[-1][0]
    view = R.assess(date)
    if os.environ.get("ANTHROPIC_API_KEY"):
        view = R.assess_llm(view)
    spec = S.choose(view)
    cands = SEL.pick(spec, date)
    qc = QC.validate(spec, cands, view, asof=date)
    msg = format_msg(date, view, spec, qc)
    ok = TG.send(msg)
    print(f"[daily] {date} 권고 발송 {'성공' if ok else '(콘솔)'} | {view.regime.value}/{view.phase} | 종목 {len(qc.approved_orders)}")

if __name__ == "__main__":
    main()
