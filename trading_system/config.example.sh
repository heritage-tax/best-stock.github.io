#!/bin/bash
# 맥미니 환경설정 예시. 복사해서 config.sh 로 만들고 값 채운 뒤: source config.sh
# (config.sh 는 비밀이므로 git에 올리지 말 것 — .gitignore 처리)

# --- 텔레그램 (필수) ---
export TELEGRAM_BOT_TOKEN="123456:ABC-...";      # @BotFather 로 발급
export TELEGRAM_CHAT_ID="123456789";              # getUpdates 로 확인

# --- 데이터 경로 ---
export YH_DIR="$HOME/trading_data/yh"             # 일봉 캐시 위치
export UNIV_CSV="$HOME/best-stock.github.io/research/kospi200.csv"
export FETCH_SCRIPT="$HOME/best-stock.github.io/research/scripts/fetch.py"

# --- 운용 파라미터 ---
export CAPITAL="10000000"                          # 운용자본(원) — 권고 금액 계산용
export EXPOSURE="1.5"                              # 튜닝 결론: 1.5x

# --- (선택) LLM 국면 보정 ---
# export ANTHROPIC_API_KEY="sk-ant-..."

# --- (선택) KIS API: 잔고·실시간 시세 ---
# export KIS_APP_KEY="..."
# export KIS_APP_SECRET="..."
# export KIS_ACCOUNT="12345678-01"
