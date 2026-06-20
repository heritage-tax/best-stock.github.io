import urllib.request, json, time, os, csv

os.makedirs('/tmp/yh', exist_ok=True)
# 동적 기간: 항상 '지금'까지 수집(내일 0시 여유), 약 3년 룩백
P2 = int(time.time()) + 86400
P1 = P2 - int(3.05 * 365 * 86400)

def fetch(sym):
    url=(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}'
         f'?period1={P1}&period2={P2}&interval=1d')
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    return urllib.request.urlopen(req,timeout=20).read()

def get(sym):
    fp=f'/tmp/yh/{sym}.json'
    if os.path.exists(fp) and os.path.getsize(fp)>200:
        return True
    for a in range(5):
        try:
            d=fetch(sym)
            j=json.loads(d)
            if j['chart']['result'] and j['chart']['result'][0].get('timestamp'):
                open(fp,'wb').write(d); return True
            return False
        except Exception as e:
            time.sleep(2+a*2)
    return False

# load tickers
syms=['^KS200']
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())
# 벤치마크(^KS11 KOSPI종합, ^KS200 지연 대체) + 하락장용 1배 인버스 ETF + 국면 보조지표(미국·변동성)
syms += ['^KS11', '114800.KS', '^GSPC', '^VIX']

ok=0; fail=[]
for i,s in enumerate(syms):
    if get(s): ok+=1
    else: fail.append(s)
    if i%25==0: print(f'{i}/{len(syms)} ok={ok}',flush=True)
    time.sleep(0.25)
print('DONE ok=',ok,'fail=',len(fail),fail[:20])
