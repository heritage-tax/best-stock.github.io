"""(B) 그래디언트부스팅 신호결합 종목선정 — (A) 규율대로 OOS로 손코딩 점수 대비 검증.
GBM이 기존 신호(RSI·이격·BB·모멘텀·변동성·신고가거리·낙폭)를 결합해 10일 수익을 예측 → 랭킹.
train(과거)에서만 학습 → embargo → OOS(미래)에서 손코딩 과매도 랭킹·KOSPI200과 비교.
python3 gbm_select.py
"""
import math
import numpy as np
import lightgbm as lgb
import data as D

FWD = 10
FEATS = ['rsi14', 'dev20', 'dev60', 'bbz', 'mom5', 'mom20', 'mom60', 'vol20', 'hi52', 'dd20']
TRAIN_END = __import__('os').environ.get('TRAIN_END','2025-03-15')
TEST_START = __import__('os').environ.get('TEST_START','2025-04-01')
COST = 0.002

idx = D.prices('^KS200'); iclose = dict(idx)

def build():
    X, code, date, tgt, hand = [], [], [], [], []
    for u in D.universe():
        p = D.prices(u['code'])
        if not p or len(p) < 320: continue
        dts = [d for d, _ in p]; C = [c for _, c in p]
        n = len(C)
        for t in range(60, n-FWD):
            sma20 = sum(C[t-19:t+1])/20; sma60 = sum(C[t-59:t+1])/60
            w = C[t-19:t+1]; sd = (sum((x-sma20)**2 for x in w)/20)**0.5
            g = l = 0
            for k in range(t-13, t+1):
                ch = C[k]-C[k-1]; g += max(ch, 0); l += max(-ch, 0)
            ag, al = g/14, l/14; rsi = 100-100/(1+ag/al) if al > 0 else 100
            rr = [C[k]/C[k-1]-1 for k in range(t-19, t+1)]; mr = sum(rr)/20
            vol = (sum((x-mr)**2 for x in rr)/20)**0.5
            dev20 = C[t]/sma20-1
            X.append([rsi, dev20, C[t]/sma60-1, (C[t]-sma20)/(2*sd) if sd > 0 else 0,
                      C[t]/C[t-5]-1, C[t]/C[t-20]-1, C[t]/C[t-60]-1, vol,
                      C[t]/max(C[max(0, t-251):t+1])-1, C[t]/max(C[t-20:t+1])-1])
            code.append(u['code']); date.append(dts[t]); tgt.append(C[t+FWD]/C[t]-1)
            hand.append((30-rsi) + (-dev20)*100)   # 손코딩 과매도 점수(높을수록 과매도)
    return (np.array(X, dtype=float), np.array(code), np.array(date),
            np.array(tgt, dtype=float), np.array(hand, dtype=float))

print("피처 빌드 중...")
X, code, date, tgt, hand = build()
tr = date <= TRAIN_END; te = date >= TEST_START
print(f"표본: train {tr.sum():,}행 / OOS {te.sum():,}행 / 피처 {len(FEATS)}개")

params = {'objective': 'regression', 'num_leaves': 15, 'learning_rate': 0.03,
          'min_child_samples': 200, 'bagging_fraction': 0.8, 'bagging_freq': 1,
          'feature_fraction': 0.8, 'seed': 0, 'verbose': -1}
booster = lgb.train(params, lgb.Dataset(X[tr], label=tgt[tr]), num_boost_round=300)
pred = booster.predict(X)

print("\n[피처 중요도(split)]")
for f, imp in sorted(zip(FEATS, booster.feature_importance()), key=lambda x: -x[1]):
    print(f"  {f:<8} {imp}")

# ----- OOS 주간 리밸런싱 롱온리 top-20 비교 -----
series = {u['code']: dict(D.prices(u['code']) or []) for u in D.universe()}
oos_dates = sorted(set(date[te]))
def weekly_topN(score_arr, N=20, rebal=5):
    # date -> ranked codes
    bydate = {}
    teidx = np.where(te)[0]
    for i in teidx:
        bydate.setdefault(date[i], []).append((score_arr[i], code[i]))
    weights = {}; eq = 1.0; rets = []
    for k, dt in enumerate(oos_dates):
        r = 0.0
        if k > 0:
            y = oos_dates[k-1]
            for c, wt in weights.items():
                s = series.get(c)
                if s and dt in s and y in s and s[y] > 0: r += wt*(s[dt]/s[y]-1)
        if k % rebal == 0 and dt in bydate:
            top = [c for _, c in sorted(bydate[dt], reverse=True)[:N]]
            new = {c: 1.0/len(top) for c in top} if top else {}
            allc = set(new) | set(weights)
            r -= sum(abs(new.get(c, 0)-weights.get(c, 0)) for c in allc)*COST
            weights = new
        eq *= (1+r); rets.append(r)
    return rets

def stat(rets):
    e = 1.0
    for r in rets: e *= (1+r)
    sd = (sum((x-sum(rets)/len(rets))**2 for x in rets)/len(rets))**0.5
    sh = (sum(rets)/len(rets))/sd*math.sqrt(252) if sd > 0 else 0
    return e-1, sh

gbm = stat(weekly_topN(pred))
hnd = stat(weekly_topN(hand))
bds = [d for d in oos_dates if d in iclose]
bench = iclose[bds[-1]]/iclose[bds[0]]-1

print("\n" + "="*56)
print(f"OOS ({oos_dates[0]}~{oos_dates[-1]}) 주간 top-20 롱온리, 비용 0.2%")
print(f"{'전략':<26}{'누적':>10}{'연Sharpe':>10}")
print('-'*56)
print(f"{'GBM 신호결합 랭킹':<24}{gbm[0]*100:>9.1f}%{gbm[1]:>10.2f}")
print(f"{'손코딩 과매도 랭킹(baseline)':<22}{hnd[0]*100:>9.1f}%{hnd[1]:>10.2f}")
print(f"{'KOSPI200 B&H':<26}{bench*100:>9.1f}%{'':>10}")
print("="*56)
verdict = "GBM 우위" if gbm[1] > hnd[1] else "baseline 우위 (GBM 무익)"
print(f">>> OOS 판정: {verdict}  (Sharpe {gbm[1]:.2f} vs {hnd[1]:.2f})")
