"""데이터층: 가격·매크로·유니버스 로드 (현재 /tmp/yh 캐시; 실거래 시 브로커 API로 교체).
반복 스캔(국면 breadth, 선정, 시뮬레이션) 속도를 위해 메모리 캐시 적용."""
import json, os, csv, math
from datetime import datetime, timezone
from functools import lru_cache

YH = os.environ.get('YH_DIR', '/tmp/yh')
UNIV_CSV = os.environ.get('UNIV_CSV', '/tmp/kospi200.csv')
KOSDAQ_CSV = os.environ.get('KOSDAQ_CSV', '')
# 벤치마크: 야후 ^KS200은 지연/누락, 069500(KODEX200)은 이상봉 多 → ^KS11(KOSPI종합, 최신·청결) 사용.
BENCH = os.environ.get('BENCH_SYMBOL', '^KS11')

@lru_cache(maxsize=4096)
def _load_raw(sym):
    fp = f'{YH}/{sym}.json'
    if not os.path.exists(fp):
        return None
    j = json.load(open(fp)); res = j['chart']['result'][0]
    ts = res['timestamp']; q = res['indicators']['quote'][0]
    adj = res['indicators']['adjclose'][0]['adjclose'] if 'adjclose' in res['indicators'] else None
    vols = q.get('volume')
    out = []
    for i, t in enumerate(ts):
        o, h, l, c = q['open'][i], q['high'][i], q['low'][i], q['close'][i]
        if c is None or c <= 0:
            continue
        ac = adj[i] if (adj and adj[i] is not None) else c
        v = (vols[i] if (vols and vols[i] is not None) else 0)
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime('%Y-%m-%d')
        out.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'adj': ac, 'vol': v})
    return tuple(out)   # hashable for cache

@lru_cache(maxsize=4096)
def prices(sym):
    raw = _load_raw(sym)
    if not raw:
        return None
    return tuple((r['date'], r['adj']) for r in raw)

@lru_cache(maxsize=4096)
def volumes(sym):
    """prices(sym)와 동일 인덱스로 정렬된 거래량 시리즈 (GBM 거래량 피처용)."""
    raw = _load_raw(sym)
    if not raw:
        return None
    return tuple(r['vol'] for r in raw)

def ohlc(sym):
    return _load_raw(sym)

def _read_csv(path, market):
    out = []
    with open(path, encoding='utf-8') as f:
        r = csv.reader(f); next(r)
        for row in r:
            if len(row) >= 3:
                out.append({'code': row[1].strip(), 'name': row[2].strip(), 'market': market})
    return out

@lru_cache(maxsize=4)
def universe(market='all'):
    syms = []
    if market in ('all', 'kospi'):
        syms += _read_csv(UNIV_CSV, 'kospi')
    if market in ('all', 'kosdaq') and KOSDAQ_CSV and os.path.exists(KOSDAQ_CSV):
        syms += _read_csv(KOSDAQ_CSV, 'kosdaq')
    return syms  # list of dicts (cached; treat as read-only)

def sma(series, n, i):
    if i < n - 1:
        return None
    return sum(series[i-n+1:i+1]) / n

def realized_vol(series, n, i):
    if i < n:
        return None
    rets = [series[k]/series[k-1]-1 for k in range(i-n+1, i+1)]
    m = sum(rets)/len(rets)
    sd = (sum((x-m)**2 for x in rets)/len(rets))**0.5
    return sd * math.sqrt(252)
