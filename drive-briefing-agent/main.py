import os
from datetime import datetime
from dotenv import load_dotenv
from src.collector import collect_news
from src.summarizer import generate_insight_briefing
from src.drive_uploader import upload_briefing_to_drive
from src.notifier import send_telegram_notification

load_dotenv()


def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    doc_title = f"[{today_str}] 글로벌 테크 & 경제 인사이트 브리핑"
    folder_id = os.environ["GOOGLE_DRIVE_FOLDER_ID"]

    # 1. RSS 뉴스 수집 및 본문 추출
    print("1️⃣ 뉴스 데이터 수집 시작...")
    raw_news = collect_news()

    # 2. Gemini API로 원인(Why)과 전망(So What) 중심 브리핑 생성
    print("2️⃣ Gemini 인사이트 분석 중...")
    briefing_md = generate_insight_briefing(raw_news)

    # 3. Google Drive에 Google Docs로 자동 업로드
    print("3️⃣ Google Drive 업로드 중...")
    doc_link = upload_briefing_to_drive(
        title=doc_title,
        markdown_content=briefing_md,
        folder_id=folder_id,
    )
    print(f"   -> 업로드 완료: {doc_link}")

    # 4. 텔레그램 알림 발송
    print("4️⃣ 텔레그램 알림 발송 중...")
    send_telegram_notification(doc_title=doc_title, doc_link=doc_link)
    print("✅ 모든 파이프라인 작업이 완료되었습니다!")


if __name__ == "__main__":
    main()
