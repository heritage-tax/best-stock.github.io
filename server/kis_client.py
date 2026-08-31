"""
한국투자증권 Open API 클라이언트 (실전투자)
"""
import os
import logging
from datetime import datetime, timedelta
import requests

log = logging.getLogger("kis")

KIS_BASE = "https://openapi.koreainvestment.com:9443"


class KISClient:
    def __init__(self):
        self.app_key = os.environ["KIS_APP_KEY"]
        self.app_secret = os.environ["KIS_APP_SECRET"]
        # 계좌번호: "XXXXXXXXXX-01" 형식
        raw = os.environ["KIS_ACCOUNT_NO"].replace("-", "")
        self.cano = raw[:8]        # 앞 8자리
        self.acnt_prdt_cd = raw[8:] or "01"  # 뒤 2자리
        self._token: str | None = None
        self._token_expires: datetime | None = None

    # ── 토큰 ──────────────────────────────────────────────
    def _get_token(self) -> str:
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token
        log.info("KIS 토큰 갱신 중...")
        r = requests.post(
            f"{KIS_BASE}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        # 만료 1시간 전에 갱신
        self._token_expires = datetime.now() + timedelta(hours=23)
        log.info("KIS 토큰 갱신 완료")
        return self._token

    def _headers(self, tr_id: str) -> dict:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    # ── 현재가 ────────────────────────────────────────────
    def get_price(self, code: str) -> dict:
        r = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._headers("FHKST01010100"),
            params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code},
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()["output"]
        return {
            "code": code,
            "name": d.get("hts_kor_isnm", code),
            "price": int(d["stck_prpr"]),
            "change_pct": float(d["prdy_ctrt"]),
            "volume": int(d["acml_vol"]),
            "high": int(d["stck_hgpr"]),
            "low": int(d["stck_lwpr"]),
        }

    # ── 잔고 / 포지션 ─────────────────────────────────────
    def get_balance(self) -> dict:
        r = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=self._headers("TTTC8434R"),
            params={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        positions = [
            {
                "code": p["pdno"],
                "name": p["prdt_name"],
                "qty": int(p["hldg_qty"]),
                "avg_price": int(float(p["pchs_avg_pric"])),
                "cur_price": int(p["prpr"]),
                "pnl": int(p["evlu_pfls_amt"]),
                "pnl_pct": float(p["evlu_pfls_rt"]),
                "value": int(p["evlu_amt"]),
            }
            for p in data.get("output1", [])
            if int(p.get("hldg_qty", 0)) > 0
        ]
        summary = data.get("output2", [{}])[0]
        return {
            "cash": int(summary.get("dnca_tot_amt", 0)),
            "total_eval": int(summary.get("tot_evlu_amt", 0)),
            "total_pnl": int(summary.get("evlu_pfls_smtl_amt", 0)),
            "total_pnl_pct": float(summary.get("evlu_pfls_smtl_rt", 0)),
            "positions": positions,
        }

    # ── 매수가능금액 ──────────────────────────────────────
    def get_buyable(self, code: str, price: int) -> int:
        r = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            headers=self._headers("TTTC8908R"),
            params={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "PDNO": code,
                "ORD_UNPR": str(price),
                "ORD_DVSN": "00",
                "CMA_EVLU_AMT_ICLD_YN": "N",
                "OVRS_ICLD_YN": "N",
            },
            timeout=10,
        )
        r.raise_for_status()
        return int(r.json()["output"].get("nrcvb_buy_qty", 0))

    # ── 주문 ─────────────────────────────────────────────
    def order(self, code: str, qty: int, price: int, side: str) -> dict:
        tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
        r = requests.post(
            f"{KIS_BASE}/uapi/domestic-stock/v1/trading/order-cash",
            headers=self._headers(tr_id),
            json={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "PDNO": code,
                "ORD_DVSN": "00",   # 지정가
                "ORD_QTY": str(qty),
                "ORD_UNPR": str(price),
            },
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()
        log.info(f"주문 {'매수' if side=='buy' else '매도'} {code} {qty}주 @{price:,} → {result.get('rt_cd')}")
        return {
            "rt_cd": result.get("rt_cd"),
            "msg": result.get("msg1", ""),
            "order_no": result.get("output", {}).get("ODNO", ""),
        }

    # ── 당일 체결 내역 ────────────────────────────────────
    def get_today_trades(self) -> list:
        r = requests.get(
            f"{KIS_BASE}/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            headers=self._headers("TTTC8001R"),
            params={
                "CANO": self.cano,
                "ACNT_PRDT_CD": self.acnt_prdt_cd,
                "INQR_STRT_DT": datetime.now().strftime("%Y%m%d"),
                "INQR_END_DT": datetime.now().strftime("%Y%m%d"),
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "01",
                "PDNO": "",
                "CCLD_DVSN": "01",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
            timeout=10,
        )
        r.raise_for_status()
        trades = []
        for t in r.json().get("output1", []):
            trades.append({
                "time": t.get("ord_tmd", ""),
                "code": t.get("pdno", ""),
                "name": t.get("prdt_name", ""),
                "side": "매도" if t.get("sll_buy_dvsn_cd") == "01" else "매수",
                "qty": int(t.get("tot_ccld_qty", 0)),
                "price": int(t.get("avg_prvs", 0)),
                "amount": int(t.get("tot_ccld_amt", 0)),
            })
        return trades
