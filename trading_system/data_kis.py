"""한국투자증권(KIS) Open API 보조 어댑터 — 잔고·현재가 조회(매도 권고·실시간 가격용).
가격 캐시는 Yahoo(fetch.py)를 기본으로 쓰고, 이 모듈은 '보유 종목 매도 권고'와
실시간 시세 확인 등 보조 기능에 사용한다.
환경변수: KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT(8자리-2자리), KIS_DOMAIN(기본 실전)
※ 실제 동작엔 본인 앱키/시크릿 + KIS 문서 확인 필요. (스켈레톤)
docs: https://apiportal.koreainvestment.com
"""
import os, json, urllib.request, urllib.parse, time

DOMAIN = os.environ.get("KIS_DOMAIN", "https://openapi.koreainvestment.com:9443")
TOKEN_FILE = os.path.expanduser(os.environ.get("KIS_TOKEN_FILE", "~/trading_data/kis_token.json"))
_token = {"v": None, "exp": 0}

def _req(path, headers, params=None, method="GET", body=None):
    url = DOMAIN + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"KIS HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")

def token():
    """접근토큰(24h 유효). KIS는 발급을 1분당 1회로 제한 → 파일 캐시로 전 프로세스 공유."""
    if _token["v"] and time.time() < _token["exp"]:
        return _token["v"]
    try:
        d = json.load(open(TOKEN_FILE))
        if time.time() < d["exp"]:
            _token.update(v=d["access_token"], exp=d["exp"]); return _token["v"]
    except Exception:
        pass
    body = {"grant_type": "client_credentials",
            "appkey": os.environ["KIS_APP_KEY"], "appsecret": os.environ["KIS_APP_SECRET"]}
    r = _req("/oauth2/tokenP", {"content-type": "application/json"}, method="POST", body=body)
    _token["v"] = r["access_token"]; _token["exp"] = time.time() + int(r.get("expires_in", 86400)) - 600
    try:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        json.dump({"access_token": _token["v"], "exp": _token["exp"]}, open(TOKEN_FILE, "w"))
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass
    return _token["v"]

def _headers(tr_id):
    return {"content-type": "application/json", "authorization": f"Bearer {token()}",
            "appkey": os.environ["KIS_APP_KEY"], "appsecret": os.environ["KIS_APP_SECRET"], "tr_id": tr_id}

def current_price(code):
    """현재가 조회 (FHKST01010100)."""
    r = _req("/uapi/domestic-stock/v1/quotations/inquire-price", _headers("FHKST01010100"),
             params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
    return int(r["output"]["stck_prpr"])  # 현재가

def balance():
    """보유 종목/평가 조회 (TTTC8434R). 매도 권고에 활용."""
    acct = os.environ["KIS_ACCOUNT"].split("-")
    r = _req("/uapi/domestic-stock/v1/trading/inquire-balance", _headers("TTTC8434R"),
             params={"CANO": acct[0], "ACNT_PRDT_CD": acct[1], "AFHR_FLPR_YN": "N",
                     "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                     "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""})
    return [{"code": x["pdno"], "name": x["prdt_name"], "qty": int(x["hldg_qty"]),
             "avg": float(x["pchs_avg_pric"]), "pl_pct": float(x["evlu_pfls_rt"])}
            for x in r.get("output1", []) if int(x["hldg_qty"]) > 0]

if __name__ == "__main__":
    print("balance:", balance())
