import os
import requests


def send_telegram_notification(doc_title: str, doc_link: str):
    """완성된 브리핑 문서 링크와 함께 텔레그램 알림을 보냅니다."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("[!] 텔레그램 설정이 없어 알림을 건너뜁니다.")
        return

    message = (
        f"🌅 <b>오늘의 글로벌 인사이트 브리핑 준비 완료!</b>\n\n"
        f"📄 <b>문서명:</b> {doc_title}\n"
        f"🔗 <a href='{doc_link}'>Google Docs에서 바로 확인하기</a>\n\n"
        f"💡 <i>NotebookLM 앱을 열고 Google Drive에서 위 문서를 선택해 오디오 개요를 생성하세요!</i>"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
