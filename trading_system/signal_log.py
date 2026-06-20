"""신호 트랙레코드 로거 — 발생한 매수/매도 신호를 기록하고, N거래일 뒤 실제 성과를 자동 채점.
'사용 = 연구': 실거래 OOS 데이터를 누적해 백테스트가 아닌 미래 실적으로 전략을 검증한다.

파일: ~/trading_data/signals.jsonl (한 줄 = 한 신호)
채점: 진입일로부터 SCORE_AFTER 거래일 경과 시 실제수익·시장대비초과 기록.

CLI:
  python3 signal_log.py          # 미채점 신호 채점 + 요약 출력
환경변수: SIGNAL_LOG, SCORE_AFTER_DAYS(기본10)
"""
import os, json, datetime
import data as D

LOG = os.path.expanduser(os.environ.get('SIGNAL_LOG', '~/trading_data/signals.jsonl'))
SCORE_AFTER = int(os.environ.get('SCORE_AFTER_DAYS', '10'))


def _load():
    if not os.path.exists(LOG):
        return []
    return [json.loads(l) for l in open(LOG, encoding='utf-8') if l.strip()]


def _save(recs):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def log_signals(side, items, regime='', date=None):
    """side: 'buy'/'sell'. items: [{code,name,entry,(stop,target,reason)} ...].
    같은 날·같은 종목·같은 side 중복은 무시(장중 반복 점검 대비)."""
    if not items:
        return 0
    date = date or datetime.date.today().isoformat()
    recs = _load()
    seen = {(r['date'], r['code'], r['side']) for r in recs}
    added = 0
    for it in items:
        k = (date, it['code'], side)
        if k in seen:
            continue
        recs.append({'date': date, 'side': side, 'code': it['code'], 'name': it.get('name', ''),
                     'entry': it.get('entry'), 'stop': it.get('stop'), 'target': it.get('target'),
                     'regime': regime, 'reason': it.get('reason', ''), 'scored': False})
        seen.add(k)
        added += 1
    if added:
        _save(recs)
    return added


def score():
    """진입 후 SCORE_AFTER 거래일 지난 미채점 신호에 실제 수익·시장대비 초과 기록."""
    recs = _load()
    if not recs:
        return 0
    idx = dict(D.prices(D.BENCH) or [])
    changed = 0
    for r in recs:
        if r.get('scored'):
            continue
        p = D.prices(r['code'])
        if not p:
            continue
        dts = [d for d, _ in p]
        C = [c for _, c in p]
        ei = next((i for i, d in enumerate(dts) if d >= r['date']), None)
        if ei is None or ei + SCORE_AFTER >= len(C):
            continue  # 아직 N일 경과 안 됨 → 다음 기회에 채점
        xi = ei + SCORE_AFTER
        ret = C[xi] / C[ei] - 1
        de, dx = dts[ei], dts[xi]
        exc = (ret - (idx[dx] / idx[de] - 1)) if (de in idx and dx in idx) else None
        r['ret'] = round(ret * 100, 2)
        r['excess'] = round(exc * 100, 2) if exc is not None else None
        r['exit_date'] = dx
        r['scored'] = True
        changed += 1
    if changed:
        _save(recs)
    return changed


def summary():
    recs = _load()
    done = [r for r in recs if r.get('scored') and r.get('excess') is not None]
    pend = [r for r in recs if not r.get('scored')]
    lines = [f"📒 트랙레코드 ({LOG})",
             f"총 {len(recs)}건 | 채점완료 {len(done)} | 대기 {len(pend)} (진입후 {SCORE_AFTER}거래일 미경과)"]
    for side in ('buy', 'sell'):
        s = [r for r in done if r['side'] == side]
        if not s:
            continue
        n = len(s)
        mret = sum(r['ret'] for r in s) / n
        mexc = sum(r['excess'] for r in s) / n
        win = sum(1 for r in s if r['ret'] > 0) / n
        wexc = sum(1 for r in s if r['excess'] > 0) / n
        lab = '매수' if side == 'buy' else '매도'
        lines.append(f"[{lab}] {n}건 | 평균수익 {mret:+.2f}% (승률 {win*100:.0f}%) | "
                     f"시장대비 {mexc:+.2f}%p (초과승 {wexc*100:.0f}%)")
    return "\n".join(lines)


if __name__ == "__main__":
    n = score()
    print(f"채점: {n}건 신규 채점\n")
    print(summary())
