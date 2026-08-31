"""
텔레그램 봇 → 맥미니 Claude Code 원격 제어

폰에서 메시지 전송 → 맥미니 Claude가 코드 짜고 실행 → 결과 텔레그램으로 회신

사용법:
  python telegram_bot.py

명령어:
  /help        - 사용법
  /status      - 서버 상태
  /clear       - 대화 기록 초기화
  아무 텍스트   - Claude에게 직접 전달 (코드 작성·실행·분석 등)
"""

import os
import sys
import time
import logging
import subprocess
from collections import deque
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
ALLOWED_CHAT   = os.environ["TELEGRAM_CHAT_ID"]
CLAUDE_CMD     = os.environ.get("CLAUDE_CMD", "claude")
MAX_REPLY_LEN  = 4000
CLAUDE_TIMEOUT = 300
MAX_HISTORY    = 10  # 최대 대화 기록 (왕복 횟수)
ALLOWED_TOOLS  = os.environ.get(
    "CLAUDE_ALLOWED_TOOLS",
    "WebSearch,WebFetch,Bash,Read,Write,Edit"
)

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# chat_id별 대화 기록 저장 {chat_id: deque([{role, content}, ...])}
chat_histories: dict[str, deque] = {}

HELP_TEXT = """🤖 *StockLens Claude 원격 제어*

*사용법*
텍스트를 그냥 보내면 Claude가 맥미니에서 실행합니다.
대화 맥락을 기억하므로 이어서 질문할 수 있습니다.

*예시*
• 삼성전자 모멘텀 전략 백테스트 코드 짜줘
• 오늘 KOSPI 마감 분석해줘
• KIS API로 잔고 조회하는 파이썬 코드 짜줘
• 현재 보유종목 손익 계산해줘

*명령어*
/help    - 이 도움말
/status  - 서버 상태 확인
/clear   - 대화 기록 초기화

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


# ── 대화 기록 관리 ────────────────────────────────────────────
def get_history(chat_id: str) -> deque:
    if chat_id not in chat_histories:
        chat_histories[chat_id] = deque(maxlen=MAX_HISTORY * 2)
    return chat_histories[chat_id]


def build_prompt(chat_id: str, user_message: str) -> str:
    history = get_history(chat_id)
    if not history:
        return user_message

    lines = ["[이전 대화 내용]"]
    for entry in history:
        role = "사용자" if entry["role"] == "user" else "어시스턴트"
        lines.append(f"{role}: {entry['content']}")
    lines.append("")
    lines.append("[현재 질문]")
    lines.append(f"사용자: {user_message}")
    lines.append("어시스턴트:")
    return "\n".join(lines)


def save_exchange(chat_id: str, user_msg: str, assistant_msg: str):
    history = get_history(chat_id)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg[:500]})


# ── Claude 실행 ───────────────────────────────────────────────
def run_claude(prompt: str) -> str:
    log.info(f"Claude 실행: {prompt[:80]}...")
    cmd = [CLAUDE_CMD, "-p", prompt, "--allowedTools", ALLOWED_TOOLS]

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

    if str(chat_id) != str(ALLOWED_CHAT):
        log.warning(f"차단된 chat_id: {chat_id}")
        return

    if text.startswith("/help") or text.startswith("/start"):
        send(chat_id, HELP_TEXT)
        return

    if text.startswith("/status"):
        history_count = len(get_history(chat_id)) // 2
        send(chat_id, (
            "✅ *맥미니 봇 실행 중*\n"
            f"• Claude CLI: `{CLAUDE_CMD}`\n"
            f"• 허용 chat_id: `{ALLOWED_CHAT}`\n"
            f"• 최대 대기: {CLAUDE_TIMEOUT}초\n"
            f"• 대화 기록: {history_count}개"
        ))
        return

    if text.startswith("/clear"):
        chat_histories.pop(chat_id, None)
        send(chat_id, "🗑️ 대화 기록이 초기화됐습니다.")
        return

    send_typing(chat_id)
    send(chat_id, "검토중...")

    prompt = build_prompt(chat_id, text)
    result = run_claude(prompt)

    save_exchange(chat_id, text, result)
    send(chat_id, result, parse_mode="")


# ── 폴링 루프 ─────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info("StockLens 텔레그램 봇 시작")
    log.info(f"허용 chat_id: {ALLOWED_CHAT}")
    log.info(f"Claude CLI: {CLAUDE_CMD}")
    log.info("=" * 50)

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
