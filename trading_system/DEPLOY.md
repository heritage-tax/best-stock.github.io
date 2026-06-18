# 배포 가이드 — 맥미니(24시간) + 회사 노트북(개발) + 텔레그램 권고

## 구성
- **맥미니 = PRODUCTION**: 매일 자동으로 권고 생성 → 텔레그램 발송. KIS API(시세·잔고 보조).
- **회사 노트북 = 개발/모니터링**: Claude Code로 전략 수정 → `git push`. 맥미니는 `git pull`.
- **GitHub repo = 동기화 허브.**  **폰 = 권고 받아 수동 매매.**

---
## A. 맥미니 1회 설정

### 1) 코드·런타임
```bash
cd ~ && git clone https://github.com/heritage-tax/best-stock.github.io.git
cd best-stock.github.io && python3 -m pip install --user pykrx   # (선택)
mkdir -p ~/trading ~/trading_data/yh
```
Claude Code 설치(개발·유지보수용): https://docs.claude.com/claude-code  →  `claude` 로그인.

### 2) 텔레그램 봇 만들기
1. 텔레그램에서 **@BotFather** → `/newbot` → 봇 토큰 발급.
2. 만든 봇과 대화 시작(아무 메시지) → 브라우저에서
   `https://api.telegram.org/bot<토큰>/getUpdates` 열어 `chat.id` 확인.

### 3) 환경설정
```bash
cp ~/best-stock.github.io/trading_system/config.example.sh ~/trading/config.sh
# config.sh 편집: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CAPITAL, 경로 등
source ~/trading/config.sh
# 연결 테스트:
cd ~/best-stock.github.io/trading_system && python3 notify_telegram.py   # 폰에 테스트 메시지 와야 함
```

### 4) 수동 1회 실행(검증)
```bash
source ~/trading/config.sh
cd ~/best-stock.github.io/trading_system && python3 daily.py    # 데이터 갱신+권고+텔레그램
```

### 5) 매일 자동 실행 (launchd, 평일 15:40)
```bash
cp com.user.trading.daily.plist ~/Library/LaunchAgents/
# plist 안의 경로/유저를 본인 것으로 수정한 뒤:
launchctl load ~/Library/LaunchAgents/com.user.trading.daily.plist
# 즉시 한번 테스트: launchctl start com.user.trading.daily ; tail ~/trading/daily.log
```
> 맥미니 시스템시계가 KST면 15:40 = 장 마감 후. 익일 시가매수 권고에 적합.
> 절전 방지: 시스템 설정 → 에너지 → "디스플레이 꺼져도 잠자기 안 함" 켜기.

---
## B. 회사 노트북 (개발/모니터링)
- claude.ai/code(웹) 또는 로컬 Claude Code로 전략 수정.
- 수정 → `git commit && git push` → 맥미니는 `daily.py` 실행 전 `git pull`(아래 옵션).
- 맥미니 plist 명령 앞에 `cd ~/best-stock.github.io && git pull -q &&` 를 넣으면 매 실행 시 최신 코드로 자동 갱신.

---
## C. (선택) KIS 연동 — 매도 권고
`config.sh`에 `KIS_APP_KEY/SECRET/ACCOUNT` 채우면 `data_kis.py`로 **보유종목 잔고**를 읽어
손절/목표 도달 시 *매도 권고*도 텔레그램에 추가할 수 있음(daily.py 확장 지점). 시세 캐시는 Yahoo 사용.

---
## D. Claude Code의 역할
- **개발·튜닝**: 전략/파라미터 수정, 백테스트(`simulate.py`,`tune.py`), 신규 아이디어 검증.
- **유지보수**: 데이터 이상·로그 점검, 월간 리뷰.
- **선택적 일일 리뷰**: `claude -p "오늘 daily.log와 권고를 검토하고 이상치 알려줘"` 를 cron에 추가 가능(토큰 비용 발생).
- 실시간 매매신호 자체는 **결정론 파이썬이 생성**(안정·재현·무료). LLM은 국면 보정·리뷰 보조.
