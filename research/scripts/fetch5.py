import urllib.request, json, time, os, csv
os.makedirs('/tmp/yh5', exist_ok=True)
def fetch(sym):
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=60d&interval=5m'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    return urllib.request.urlopen(req,timeout=20).read()
def get(sym):
    fp=f'/tmp/yh5/{sym}.json'
    if os.path.exists(fp) and os.path.getsize(fp)>200: return True
    for a in range(2):
        try:
            d=fetch(sym); j=json.loads(d)
            if j['chart']['result'] and j['chart']['result'][0].get('timestamp'):
                open(fp,'wb').write(d); return True
            return False
        except Exception:
            time.sleep(1.5+a)
    return False
syms=['^KS200']
with open('/tmp/kospi200.csv',encoding='utf-8') as f:
    r=csv.reader(f); next(r)
    for row in r:
        if len(row)>=2: syms.append(row[1].strip())
ok=0;fail=0
for i,s in enumerate(syms):
    if get(s): ok+=1
    else: fail+=1
    if i%25==0: print(f'{i}/{len(syms)} ok={ok}',flush=True)
    time.sleep(0.2)
print('DONE ok=',ok,'fail=',fail)
