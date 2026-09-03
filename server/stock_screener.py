"""
주간 주식 스크리닝 & 투자 종목 리포트
매주 월요일 07:00 Claude가 성장 산업 분석 + 종목 추천 → 텔레그램 전송

실행:
  python3 stock_screener.py          # 즉시 한 번 실행
  python3 stock_screener.py --schedule  # 매주 월요일 07:00 자동 실행
"""

import os
import sys
import time
import logging
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("screener")

BOT_TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID        = os.environ["TELEGRAM_CHAT_ID"]
CLAUDE_CMD     = os.environ.get("CLAUDE_CMD", "claude")
CLAUDE_TIMEOUT = 300

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PROMPT = """오늘 날짜 기준으로 향후 12개월 성장 가능성이 높은 산업과 한국 주식 투자 종목을 분석해줘.

WebSearch로 아래 내용을 검색해서 분석할 것:
- 글로벌 메가트렌드 (AI, 반도체, 바이오, 에너지전환, 방산 등)
- 한국 증시 주도 섹터 최근 흐름
- 기관/외국인 순매수 종목
- 실적 개선 예상 종목
- 밸류에이션 저평가 우량주

아래 형식으로 plain text로 작성 (마크다운 기호 없이):

================================================
주간 투자 스크리닝 리포트 (YYYY-MM-DD)
================================================

[핵심 시장 환경]
현재 시장 상황 2~3줄 요약

------------------------------------------------
[주목 산업 TOP 3]

1. 산업명
   성장 근거: (구체적 수치나 정책 포함)
   투자 포인트:
   주의사항:

2. 산업명
   성장 근거:
   투자 포인트:
   주의사항:

3. 산업명
   성장 근거:
   투자 포인트:
   주의사항:

------------------------------------------------
[추천 종목]

종목1 (코드: XXXXXX)
  현재가:
  목표가:
  추천 이유: (실적/밸류/기술적 근거)
  리스크:

종목2 (코드: XXXXXX)
  현재가:
  목표가:
  추천 이유:
  리스크:

종목3 (코드: XXXXXX)
  현재가:
  목표가:
  추천 이유:
  리스크:

------------------------------------------------
[이번 주 주의 종목]
피해야 할 섹터나 종목 1~2개와 이유

[종합 의견]
한 줄 핵심 전략
================================================

※ 이 리포트는 참고용이며 투자 결정은 본인 판단으로 하세요."""


def send(text: str):
    max_len = 4000
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at < 100:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for chunk in chunks:
        try:
            requests.post(
                f"{TG_API}/sendMessage",
                data={
                    "chat_id": CHAT_ID,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"전송 실패: {e}")


def run_screening():
    log.info("주간 스크리닝 시작...")
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = PROMPT.replace("YYYY-MM-DD", today)

    send(f"📊 주간 투자 스크리닝 리포트 생성 중... ({today})")

    cmd = [CLAUDE_CMD, "-p", prompt, "--allowedTools", "WebSearch,WebFetch"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(Path.home()),
        )
        output = result.stdout.strip()
        if not output:
            output = "⚠️ 스크리닝 결과를 가져오지 못했습니다. 잠시 후 다시 시도하세요."
        log.info("분석 완료, 전송 중...")
        send(output)
        log.info("전송 완료")
    except subprocess.TimeoutExpired:
        send(f"⏱️ 분석 시간 초과 ({CLAUDE_TIMEOUT}초). 잠시 후 다시 시도하세요.")
    except Exception as e:
        log.error(f"오류: {e}")
        send(f"❌ 스크리닝 오류: {e}")


def run_scheduler():
    log.info("스크리닝 스케줄러 시작 (매주 월요일 07:00)")
    while True:
        now = datetime.now()
        # 월요일(0) 07:00
        if now.weekday() == 0 and now.hour == 7 and now.minute == 0:
            run_screening()
            time.sleep(60)
        time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", action="store_true", help="매주 월요일 07:00 자동 실행")
    args = parser.parse_args()

    if args.schedule:
        run_scheduler()
    else:
        run_screening()
