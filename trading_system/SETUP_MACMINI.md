# 맥미니 1회 셋업 — 자동 신호 + 원격조종 + 영구저장

맥미니 **터미널**(또는 거기 켜둔 **Claude Code**)에 아래를 순서대로 실행/지시하면,
이후엔 *손 안 대도* 장중 자동으로 텔레그램 신호가 오고, 회사에서도 원격으로 점검할 수 있습니다.

> 전제: 맥미니에 Python3·git 설치됨. **GitHub 쓰기권한 해결됨** → 이제 zip 수동전달 없이
> 맥미니에서 바로 `git clone` 으로 최신 코드를 받습니다.

## A. 최신 코드 가져오기 (git clone)
```bash
cd ~
git clone -b claude/quirky-johnson-i2w002 https://github.com/heritage-tax/best-stock.github.io.git
cd ~/best-stock.github.io
ls trading_system/        # monitor.py, daily.py, gbm_model.py ... 확인
```
> 이미 클론해 둔 적 있으면: `cd ~/best-stock.github.io && git pull origin claude/quirky-johnson-i2w002`

## B. 의존성
```bash
python3 -m pip install --user lightgbm numpy
```

## C. 설정 (config.sh)
```bash
mkdir -p ~/trading ~/trading_data/yh
cp ~/best-stock.github.io/trading_system/config.example.sh ~/trading/config.sh
nano ~/trading/config.sh    # 아래 값 채우기
```
`config.sh`에 반드시:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (@BotFather로 봇 생성 → getUpdates로 chat_id)
- `CAPITAL`(운용자본), `EXPOSURE=1.5`
- `YH_DIR=$HOME/trading_data/yh`, `UNIV_CSV=$HOME/best-stock.github.io/research/kospi200.csv`,
  `FETCH_SCRIPT=$HOME/best-stock.github.io/research/scripts/fetch.py`
- (실시간가·매도신호용) `KIS_APP_KEY/SECRET/ACCOUNT`

## D. 첫 실행·검증
```bash
source ~/trading/config.sh
cd ~/best-stock.github.io/trading_system
python3 ../research/scripts/fetch.py      # 최초 일봉 수집 (몇 분)
python3 gbm_model.py                       # GBM 모델 학습·저장
python3 notify_telegram.py                 # 폰에 테스트 메시지 와야 함
python3 monitor.py --once                  # 현재 신호 1회 점검(콘솔)
python3 daily.py --no-fetch                # 마감용 권고 형식 확인
```

## E. 자동 실행 (launchd) — 손 안 대도 돌게
```bash
cd ~/best-stock.github.io/trading_system
cp com.user.trading.monitor.plist ~/Library/LaunchAgents/   # 장중 실시간
cp com.user.trading.daily.plist   ~/Library/LaunchAgents/   # 마감 후 권고
# plist 안의 $HOME/경로가 본인 것과 맞는지 확인 후:
launchctl load ~/Library/LaunchAgents/com.user.trading.monitor.plist
launchctl load ~/Library/LaunchAgents/com.user.trading.daily.plist
tail -f ~/trading/monitor.log
```
**24시간 유지 필수 설정:**
```bash
sudo pmset -a sleep 0 disablesleep 1       # 잠자기 방지(헤드리스 Mac mini)
```
- 시스템 설정 → 사용자 및 그룹 → **자동 로그인 켜기**(재부팅 후에도 LaunchAgent 동작)
- 시스템 설정 → 에너지 → "정전 후 자동 시작" 켜기

## F. 회사에서 원격조종 (택1)
- **Tailscale(권장, 쉬움)**: 맥미니·폰·노트북에 [tailscale.com] 설치 → `tailscale up` →
  회사에서 `ssh 사용자@맥미니이름` 으로 안전 접속(인터넷에 SSH 직접 노출 X).
- **Claude 원격조종**: 맥미니에서 `claude --remote-control` 실행 → claude.ai/모바일앱에서 그 세션 조종
  (docs: code.claude.com/docs/en/remote-control). *트레이딩 신호는 위 launchd가 자동으로 하므로,
  이건 점검·수정용.*

## G. ★영구저장 해결 — 맥미니에서 GitHub로 push
지금까지 푸시가 막힌 건 *클라우드 세션*의 권한 문제일 뿐, **맥미니의 당신 GitHub 계정은 쓰기 가능**합니다.
맥미니에서 한 번 올려두면 이후 노트북·클라우드 어디서나 동기화됩니다:
```bash
cd ~/best-stock.github.io
git init 2>/dev/null; git checkout -b claude/quirky-johnson-i2w002 2>/dev/null
git remote add origin https://github.com/heritage-tax/best-stock.github.io.git 2>/dev/null
git add trading_system research DEPLOY.md
git -c user.email="당신메일" commit -m "Add trading system + research"
git push -u origin claude/quirky-johnson-i2w002      # 맥미니=당신 계정 → 성공
```
→ 이후 회사 노트북/클라우드에서 `git pull` 로 항상 최신 동기화. **zip 수동전달 끝.**

---
요약: A~D(설치·검증) → E(자동) → F(원격) → G(영구저장). E까지만 해도 "켜두면 자동 신호"는 완성.
