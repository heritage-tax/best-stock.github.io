
---
## E. 실시간 모니터링 데몬 (monitor.py) — 장중 매수/매도 신호
`daily.py`(장 마감 후 1회)와 별개로, **장중 실시간** 신호를 원하면 상주 데몬을 띄운다.
- KIS 실시간가를 '오늘 종가'로 주입해 전략 신호 재계산 + GBM 재랭킹 → 상위 슬롯 신규 진입 시 매수신호.
- KIS 보유잔고가 평균선 복귀(익절)/−10% 손절 도달 시 매도신호.
- 신호는 당일 1회만(중복방지). 09:00~15:30 KST에만 동작.

```bash
# 테스트(1회):  source ~/trading/config.sh && python3 monitor.py --once
# 상주 데몬 등록:
cp com.user.trading.monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.trading.monitor.plist
tail -f ~/trading/monitor.log
```
환경변수: `MONITOR_INTERVAL`(기본 300초), `STOP_PCT`(기본 -0.10), `WATCH_MAX`(기본 200), `KIS_APP_KEY/SECRET/ACCOUNT`(매도신호엔 잔고조회 필요).
> KIS 미연결이면 마지막 종가로 폴백(매수 스캔은 동작하나 실시간성 없음, 매도신호는 잔고 없어 미발생).
> daily.py = 마감 후 권고 / monitor.py = 장중 실시간 — 둘 다 켜도 되고, 하나만 써도 됨.
