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
echo "✅ StockLens 트레이딩 서버 시작"
echo "   포트: ${PORT:-8000}"
echo "   계좌: ${KIS_ACCOUNT_NO}"
echo ""

python main.py
