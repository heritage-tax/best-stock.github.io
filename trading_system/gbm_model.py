"""GBM 신호결합 모델 (production) — 학습·저장·로드·예측 + 월1회 재학습 판단.
기존 신호(RSI·이격·BB·모멘텀·변동성·신고가거리·낙폭)를 결합해 10일 수익을 예측.
모델은 디스크(gbm_model.txt)에 저장 → daily.py는 매일 재학습하지 않고 로드만, 30일 경과 시 재학습.
lightgbm 미설치/모델 없음 시 selection.py가 손코딩 점수로 자동 폴백.
"""
import os, json, time
import data as D

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.environ.get('GBM_MODEL', os.path.join(HERE, 'gbm_model.txt'))
META_PATH = MODEL_PATH + '.meta.json'
FWD = 10
PARAMS = {'objective': 'regression', 'num_leaves': 15, 'learning_rate': 0.03,
          'min_child_samples': 200, 'bagging_fraction': 0.8, 'bagging_freq': 1,
          'feature_fraction': 0.8, 'seed': 0, 'verbose': -1}

FEATURE_NAMES = ['rsi', 'dev_sma20', 'dev_sma60', 'bb_pos', 'mom5', 'mom20', 'mom60',
                 'vol', 'dist_52w_high', 'dist_20d_high', 'vol_ratio', 'vol_trend']

def features(C, i, V=None):
    """index i 시점 피처(과거만 사용). 부족하면 None. V(거래량) 있으면 거래량 피처 2개 추가."""
    if i < 60:
        return None
    sma20 = sum(C[i-19:i+1])/20; sma60 = sum(C[i-59:i+1])/60
    w = C[i-19:i+1]; sd = (sum((x-sma20)**2 for x in w)/20)**0.5
    g = l = 0
    for k in range(i-13, i+1):
        ch = C[k]-C[k-1]; g += max(ch, 0); l += max(-ch, 0)
    ag, al = g/14, l/14; rsi = 100-100/(1+ag/al) if al > 0 else 100
    rr = [C[k]/C[k-1]-1 for k in range(i-19, i+1)]; mr = sum(rr)/20
    vol = (sum((x-mr)**2 for x in rr)/20)**0.5
    # 거래량 피처: 당일 거래량/20일평균(투매·관심 급증), 5일평균/20일평균(거래량 추세)
    if V is not None and len(V) > i and i >= 20:
        va20 = sum(V[i-19:i+1])/20
        vr = (V[i]/va20) if va20 > 0 else 1.0
        vt = (sum(V[i-4:i+1])/5 / va20) if va20 > 0 else 1.0
    else:
        vr = 1.0; vt = 1.0
    return [rsi, C[i]/sma20-1, C[i]/sma60-1, (C[i]-sma20)/(2*sd) if sd > 0 else 0,
            C[i]/C[i-5]-1, C[i]/C[i-20]-1, C[i]/C[i-60]-1, vol,
            C[i]/max(C[max(0, i-251):i+1])-1, C[i]/max(C[i-20:i+1])-1,
            vr, vt]

def _build_training(asof):
    X, y = [], []
    for u in D.universe():
        p = D.prices(u['code'])
        if not p or len(p) < 320: continue
        dts = [d for d, _ in p]; C = [c for _, c in p]
        v = D.volumes(u['code']); V = list(v) if v else None
        for t in range(60, len(C)-FWD):
            if dts[t+FWD] > asof:      # 타깃이 asof 시점에 아직 실현 안 됨 → 누수 방지
                break
            f = features(C, t, V)
            if f: X.append(f); y.append(C[t+FWD]/C[t]-1)
    return X, y

def train(asof=None, path=MODEL_PATH):
    """asof(미지정 시 최신일)까지 데이터로 학습 후 저장."""
    import numpy as np, lightgbm as lgb
    asof = asof or D.prices('^KS200')[-1][0]
    X, y = _build_training(asof)
    if len(y) < 1000:
        raise RuntimeError(f"학습표본 부족({len(y)})")
    booster = lgb.train(PARAMS, lgb.Dataset(np.array(X), label=np.array(y)), num_boost_round=300)
    booster.save_model(path)
    json.dump({'trained_on': asof, 'ts': time.time(), 'n': len(y)}, open(path+'.meta.json', 'w'))
    return booster, len(y)

_M = {'loaded': False, 'b': None}
def active_model(path=MODEL_PATH):
    """모델 1회 로드 캐시. 없거나 lightgbm 미설치면 None(폴백)."""
    if not _M['loaded']:
        _M['loaded'] = True
        try:
            import lightgbm as lgb
            if os.path.exists(path):
                _M['b'] = lgb.Booster(model_file=path)
        except Exception:
            _M['b'] = None
    return _M['b']

def predict_at(booster, C, i, V=None):
    import numpy as np
    f = features(C, i, V)
    if f is None: return None
    return float(booster.predict(np.array([f]))[0])

def needs_retrain(path=MODEL_PATH, max_age_days=30):
    mp = path+'.meta.json'
    if not os.path.exists(path) or not os.path.exists(mp):
        return True
    try:
        return (time.time()-json.load(open(mp)).get('ts', 0)) > max_age_days*86400
    except Exception:
        return True

if __name__ == '__main__':
    b, n = train()
    print(f"학습 완료: {n:,}행, 저장 → {MODEL_PATH}")
