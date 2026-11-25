import io
import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Google Drive 파일 생성 권한 스코프
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    """저장된 token.json으로 인증하거나, 없으면 최초 1회 OAuth 로그인을 수행합니다."""
    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        # 갱신/생성된 토큰 저장
        token_path.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def upload_briefing_to_drive(title: str, markdown_content: str, folder_id: str) -> str:
    """
    마크다운 브리핑 내용을 지정된 Google Drive 폴더에 'Google Docs' 문서로 변환해 업로드하고,
    생성된 문서의 웹 링크를 반환합니다.
    """
    service = get_drive_service()

    file_metadata = {
        "name": title,
        "parents": [folder_id],
        # 핵심: 일반 텍스트가 아닌 Google Docs 포맷으로 자동 변환하여 저장
        "mimeType": "application/vnd.google-apps.document",
    }

    # 마크다운 문자열을 메모리 스트림으로 변환하여 업로드
    media = MediaIoBaseUpload(
        io.BytesIO(markdown_content.encode("utf-8")),
        mimetype="text/markdown",
        resumable=True,
    )

    uploaded_file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )

    return uploaded_file.get("webViewLink", "")
