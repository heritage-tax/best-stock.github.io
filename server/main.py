"""
StockLens 트레이딩 서버 — FastAPI
맥미니에서 24시간 실행, 폰 브라우저로 원격 제어
"""
import os
import logging
from datetime import datetime
from collections import deque

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from kis_client import KISClient

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("server")

app = FastAPI(title="StockLens Trading Server")

# CORS — GitHub Pages + 로컬 테스트 허용
ALLOWED_ORIGINS = [
    "https://heritage-tax.github.io",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 상태
kis = KISClient()
trading_active = False       # 기본값: 비활성 (수동으로 켜야 함)
current_strategy = "모멘텀"
signal_log: deque = deque(maxlen=100)   # 최근 100개 신호 보관
CONTROL_SECRET = os.environ["CONTROL_SECRET"]


# ── 인증 ─────────────────────────────────────────────────
def verify(x_secret: str = Header(...)):
    if x_secret != CONTROL_SECRET:
        raise HTTPException(status_code=403, detail="인증 실패")


def add_log(kind: str, msg: str):
    signal_log.appendleft({
        "time": datetime.now().strftime("%H:%M:%S"),
        "kind": kind,
        "msg": msg,
    })


# ── 요청 스키마 ───────────────────────────────────────────
class OrderReq(BaseModel):
    code: str
    qty: int
    price: int
    side: str   # "buy" | "sell"

class StrategyReq(BaseModel):
    name: str


# ── 공개 엔드포인트 ───────────────────────────────────────
@app.get("/api/status")
def status():
    return {
        "ok": True,
        "trading_active": trading_active,
        "strategy": current_strategy,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

@app.get("/api/price/{code}")
def price(code: str):
    try:
        return kis.get_price(code)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── 인증 필요 엔드포인트 ──────────────────────────────────
@app.get("/api/balance", dependencies=[Depends(verify)])
def balance():
    try:
        return kis.get_balance()
    except Exception as e:
        log.error(f"잔고조회 실패: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/trades", dependencies=[Depends(verify)])
def trades():
    try:
        return {"trades": kis.get_today_trades()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/signals", dependencies=[Depends(verify)])
def signals():
    return {"signals": list(signal_log)}

@app.post("/api/order", dependencies=[Depends(verify)])
def order(req: OrderReq):
    if req.side not in ("buy", "sell"):
        raise HTTPException(400, "side는 buy 또는 sell")
    if req.qty <= 0:
        raise HTTPException(400, "수량은 1 이상")
    if req.price <= 0:
        raise HTTPException(400, "가격은 0 초과")
    try:
        result = kis.order(req.code, req.qty, req.price, req.side)
        side_kr = "매수" if req.side == "buy" else "매도"
        add_log(req.side, f"{side_kr} 주문: {req.code} {req.qty}주 @{req.price:,}원 → {result['msg']}")
        return result
    except Exception as e:
        log.error(f"주문 실패: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/system/toggle", dependencies=[Depends(verify)])
def toggle():
    global trading_active
    trading_active = not trading_active
    state = "활성화" if trading_active else "비활성화"
    add_log("info", f"시스템 {state}")
    log.info(f"트레이딩 시스템 {state}")
    return {"trading_active": trading_active}

@app.post("/api/strategy", dependencies=[Depends(verify)])
def set_strategy(req: StrategyReq):
    global current_strategy
    current_strategy = req.name
    add_log("info", f"전략 변경 → {req.name}")
    return {"strategy": current_strategy}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
