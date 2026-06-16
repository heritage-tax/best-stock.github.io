"""조정자: 국면판단→전략결정→종목선정→QC 검증 + 리포트. python3 orchestrator.py [YYYY-MM-DD]"""
import sys
import data as D, regime as R, strategy as S, selection as SEL, qc as QC

def run(date=None):
    ks = D.prices('^KS200'); date = date or ks[-1][0]
    view = R.assess(date); view = R.assess_llm(view)
    spec = S.choose(view)
    cands = SEL.pick(spec, date)
    qc = QC.validate(spec, cands, view, asof=date)
    print("="*70)
    print(f"[기준일] {date}")
    print(f"[1. 국면판단] {view.regime.value} · {view.phase}  (score={view.score}, conf={view.confidence}, {view.source})")
    print(f"             {view.rationale}")
    print(f"[2. 전략결정] {spec.name}\n             {spec.note}")
    print(f"[3. 종목선정] {len(cands)}개 후보 (상위 {min(len(cands),10)})")
    for c in cands[:10]:
        print(f"   - {c.name:<16}({c.code})  진입 {c.entry:>10,.0f} 손절 {c.stop:>10,.0f} 목표 {c.target:>10,.0f} | {c.reason}")
    print(f"[4. QC검증] {'승인' if qc.approved else '반려/현금'}  주문 {len(qc.approved_orders)}건")
    for r in qc.reasons: print(f"   · {r}")
    print("="*70)
    return qc

if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else None)
