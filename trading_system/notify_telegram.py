"""텔레그램 알림 발송. 환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
봇 생성: @BotFather 에게 /newbot → 토큰 발급. chat_id: 봇과 대화 시작 후
https://api.telegram.org/bot<TOKEN>/getUpdates 에서 확인.
"""
import os, json, urllib.request, urllib.parse

def send(text: str, parse_mode: str = "Markdown") -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — 콘솔 출력만:\n" + text)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "parse_mode": parse_mode,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15)
        return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[telegram] 발송 실패: {e}\n{text}")
        return False

if __name__ == "__main__":
    send("✅ 트레이딩 시스템 텔레그램 연결 테스트 OK")
