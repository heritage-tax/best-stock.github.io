#!/bin/bash
# ======================================================
#  맥미니 서버 시작 스크립트
#  터미널에서: chmod +x start.sh && ./start.sh
# ======================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# .env 로드
if [ ! -f .env ]; then
  echo "❌ .env 파일이 없습니다. .env.template을 복사해 .env로 저장하세요."
  exit 1
fi
export $(grep -v '^#' .env | xargs)

# 가상환경 생성 (처음 한 번만)
if [ ! -d venv ]; then
  echo "🔧 가상환경 생성 중..."
  python3 -m venv venv
fi

source venv/bin/activate

# 패키지 설치
pip install -q -r requirements.txt

echo ""
echo "✅ StockLens 서버 시작"
echo "   포트: ${PORT:-8000}"
echo "   계좌: ${KIS_ACCOUNT_NO}"
echo "   텔레그램 봇: ${TELEGRAM_BOT_TOKEN:0:10}..."
echo ""

# 텔레그램 봇을 백그라운드에서 실행
python telegram_bot.py &
BOT_PID=$!
echo "📱 텔레그램 봇 PID: $BOT_PID"

# FastAPI 서버 실행 (포어그라운드)
python main.py

# 서버 종료 시 봇도 종료
kill $BOT_PID 2>/dev/null
