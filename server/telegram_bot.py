"""
텔레그램 봇 → 맥미니 Claude Code 원격 제어

폰에서 메시지 전송 → 맥미니 Claude가 코드 짜고 실행 → 결과 텔레그램으로 회신

사용법:
  python telegram_bot.py

명령어:
  /help        - 사용법
  /status      - 서버 상태
  아무 텍스트   - Claude에게 직접 전달 (코드 작성·실행·분석 등)
"""

import os
import sys
import time
import logging
import subprocess
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tg_bot")

BOT_TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_CHAT   = os.environ["TELEGRAM_CHAT_ID"]   # 본인 chat_id만 허용
CLAUDE_CMD     = os.environ.get("CLAUDE_CMD", "claude")  # claude CLI 경로
MAX_REPLY_LEN  = 4000   # 텔레그램 메시지 최대 길이
CLAUDE_TIMEOUT = 300    # Claude 응답 대기 최대 5분

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HELP_TEXT = """🤖 *StockLens Claude 원격 제어*

*사용법*
텍스트를 그냥 보내면 Claude가 맥미니에서 실행합니다.

*예시*
• 삼성전자 모멘텀 전략 백테스트 코드 짜줘
• 오늘 KOSPI 마감 분석해줘
• KIS API로 잔고 조회하는 파이썬 코드 짜줘
• 현재 보유종목 손익 계산해줘

*명령어*
/help    - 이 도움말
/status  - 서버 상태 확인

⚠️ 코드 실행 결과는 최대 5분 내로 회신됩니다."""


# ── 텔레그램 API ─────────────────────────────────────────────
def tg_get(method: str, params: dict = None):
    try:
        r = requests.get(f"{TG_API}/{method}", params=params, timeout=30)
        return r.json()
    except Exception as e:
        log.warning(f"tg_get {method} 실패: {e}")
        return {}


def send(chat_id: str, text: str, parse_mode: str = "Markdown"):
    """4000자 초과 시 자동 분할 전송."""
    if not text.strip():
        text = "(응답 없음)"

    chunks = []
    while len(text) > MAX_REPLY_LEN:
        split_at = text.rfind("\n", 0, MAX_REPLY_LEN)
        if split_at < 100:
            split_at = MAX_REPLY_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)

    for chunk in chunks:
        try:
            requests.post(
                f"{TG_API}/sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
        except Exception as e:
            log.warning(f"send 실패: {e}")


def send_typing(chat_id: str):
    tg_get("sendChatAction", {"chat_id": chat_id, "action": "typing"})


# ── Claude 실행 ───────────────────────────────────────────────
def run_claude(prompt: str) -> str:
    """
    맥미니에 설치된 claude CLI를 print(-p) 모드로 실행.
    claude -p "prompt"
    """
    log.info(f"Claude 실행: {prompt[:80]}...")

    cmd = [CLAUDE_CMD, "-p", prompt]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(Path.home()),
        )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            output = (output + "\n\n⚠️ stderr:\n" + result.stderr[:500]).strip()
        return output or "(Claude 출력 없음)"
    except subprocess.TimeoutExpired:
        return f"⏱️ 시간 초과 ({CLAUDE_TIMEOUT}초). 더 간단한 요청을 시도해보세요."
    except FileNotFoundError:
        return (
            "❌ `claude` 명령어를 찾을 수 없습니다.\n"
            "맥미니에 Claude Code CLI가 설치되어 있는지 확인하세요:\n"
            "`npm install -g @anthropic-ai/claude-code`"
        )
    except Exception as e:
        log.error(f"Claude 실행 오류: {e}")
        return f"❌ 실행 오류: {e}"


# ── 메시지 처리 ───────────────────────────────────────────────
def handle(chat_id: str, text: str):
    text = text.strip()

    # 보안: 허용된 chat_id만
    if str(chat_id) != str(ALLOWED_CHAT):
        log.warning(f"차단된 chat_id: {chat_id}")
        return

    if text.startswith("/help") or text.startswith("/start"):
        send(chat_id, HELP_TEXT)
        return

    if text.startswith("/status"):
        send(chat_id, (
            "✅ *맥미니 봇 실행 중*\n"
            f"• Claude CLI: `{CLAUDE_CMD}`\n"
            f"• 허용 chat_id: `{ALLOWED_CHAT}`\n"
            f"• 최대 대기: {CLAUDE_TIMEOUT}초"
        ))
        return

    # 나머지는 Claude에게 전달
    send_typing(chat_id)
    send(chat_id, "⏳ Claude가 작업 중입니다...")

    result = run_claude(text)

    # 결과가 길면 코드블록으로 감싸지 않음 (마크다운 충돌 방지)
    send(chat_id, result, parse_mode="")


# ── 폴링 루프 ─────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info("StockLens 텔레그램 봇 시작")
    log.info(f"허용 chat_id: {ALLOWED_CHAT}")
    log.info(f"Claude CLI: {CLAUDE_CMD}")
    log.info("=" * 50)

    # 봇 정보 확인
    me = tg_get("getMe")
    if me.get("ok"):
        bot_name = me["result"]["username"]
        log.info(f"봇 이름: @{bot_name}")
        send(ALLOWED_CHAT, f"✅ @{bot_name} 시작됨. `/help` 로 사용법 확인.")
    else:
        log.error("봇 토큰 오류. .env의 TELEGRAM_BOT_TOKEN 확인.")
        sys.exit(1)

    offset = 0
    while True:
        try:
            data = tg_get("getUpdates", {
                "offset": offset,
                "timeout": 20,
                "allowed_updates": ["message"],
            })
            updates = data.get("result", [])

            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "").strip()
                if chat_id and text:
                    log.info(f"수신 [{chat_id}]: {text[:60]}")
                    handle(chat_id, text)

        except KeyboardInterrupt:
            log.info("봇 종료")
            sys.exit(0)
        except Exception as e:
            log.warning(f"폴링 오류: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
