"""
조세뉴스 일일 브리핑
매일 08:00 Claude가 최신 조세·세법 뉴스를 요약해서 텔레그램으로 전송

실행:
  python3 tax_news.py          # 즉시 한 번 실행
  python3 tax_news.py --schedule  # 매일 08:00 자동 실행
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
log = logging.getLogger("tax_news")

BOT_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID       = os.environ["TELEGRAM_CHAT_ID"]
CLAUDE_CMD    = os.environ.get("CLAUDE_CMD", "claude")
CLAUDE_TIMEOUT = 180

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PROMPT = """오늘 날짜 기준으로 한국 조세·세법 관련 최신 뉴스를 WebSearch로 검색해서 아래 형식으로 요약해줘.

검색 키워드: "조세 뉴스 오늘", "세법 개정", "국세청 공지", "기획재정부 세제", "부동산세금", "법인세 소득세"

출력 형식 (텔레그램 메시지용, 마크다운 없이 plain text):
---
📋 오늘의 조세뉴스 브리핑 (YYYY-MM-DD)

1. [제목]
   - 핵심내용 1~2줄
   - 영향: 누구에게 어떤 영향

2. [제목]
   - 핵심내용 1~2줄
   - 영향: 누구에게 어떤 영향

(3~5개 항목)

💡 오늘의 포인트:
가장 중요한 내용 한 줄 요약
---

뉴스가 없으면 "오늘 주요 조세뉴스 없음" 이라고만 답해줘."""


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
        except Exception as e:
            log.warning(f"전송 실패: {e}")


def fetch_and_send():
    log.info("조세뉴스 브리핑 시작...")
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = PROMPT.replace("YYYY-MM-DD", today)

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
            output = "⚠️ 오늘 조세뉴스를 가져오지 못했습니다."
        log.info("브리핑 완료, 텔레그램 전송 중...")
        send(output)
        log.info("전송 완료")
    except subprocess.TimeoutExpired:
        send("⏱️ 조세뉴스 조회 시간 초과")
    except Exception as e:
        log.error(f"오류: {e}")
        send(f"❌ 조세뉴스 브리핑 오류: {e}")


def run_scheduler():
    log.info("조세뉴스 스케줄러 시작 (매일 08:00)")
    while True:
        now = datetime.now()
        if now.hour == 8 and now.minute == 0:
            fetch_and_send()
            time.sleep(60)  # 같은 분에 중복 실행 방지
        time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule", action="store_true", help="매일 08:00 자동 실행")
    args = parser.parse_args()

    if args.schedule:
        run_scheduler()
    else:
        fetch_and_send()
