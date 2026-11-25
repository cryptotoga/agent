import calendar
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser
import trafilatura

# 기수집 URL 기록 파일 경로 (프로젝트 루트 디렉토리에 자동 생성)
SEEN_URLS_FILE = Path(__file__).resolve().parent.parent / "seen_urls.json"
RETENTION_DAYS = 14  # 기록 유지 기간 (14일 경과 시 자동 삭제)

# 매체별 성격에 맞춰 수집 개수(limit) 차등 배분
RSS_FEEDS = [
    {
        "name": "Hacker News (인기 기술)",
        "url": "https://hnrss.org/frontpage?points=100",
        "category": "Tech",
        "limit": 3,
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "category": "Tech & Future",
        "limit": 2,
    },
    {
        "name": "GeekNews (국내/글로벌 테크)",
        "url": "https://news.hada.io/rss/news",
        "category": "Tech",
        "limit": 5,
    },
    {
        "name": "한국경제 (경제/금융)",
        "url": "https://www.hankyung.com/feed/economy",
        "category": "Economy & Finance",
        "limit": 5,
    },
    {
        "name": "Project Syndicate (거시/지정학 칼럼)",
        "url": "https://www.project-syndicate.org/rss",
        "category": "Macro & Geopolitics",
        "limit": 3,
    },
]


def _load_seen_urls() -> dict[str, str]:
    """
    seen_urls.json에서 기존 수집 기록({url: iso_timestamp})을 불러오고,
    14일(RETENTION_DAYS)이 지난 오래된 기록은 자동으로 정리합니다.
    """
    if not SEEN_URLS_FILE.exists():
        return {}

    try:
        raw_data = json.loads(SEEN_URLS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    cleaned_data: dict[str, str] = {}

    for url, saved_at_str in raw_data.items():
        try:
            saved_dt = datetime.fromisoformat(saved_at_str)
            if saved_dt >= cutoff_dt:
                cleaned_data[url] = saved_at_str
        except ValueError:
            continue

    return cleaned_data


def _save_seen_urls(seen_data: dict[str, str]) -> None:
    """갱신된 수집 URL 기록을 seen_urls.json에 저장합니다."""
    SEEN_URLS_FILE.write_text(
        json.dumps(seen_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _is_within_hours(entry, hours: int) -> bool:
    """발행 시각이 현재로부터 지정된 hours 이내인지 확인합니다."""
    time_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not time_struct:
        return True

    published_dt = datetime.fromtimestamp(
        calendar.timegm(time_struct), tz=timezone.utc
    )
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return published_dt >= cutoff_dt


def _fetch_article_content(url: str, fallback_summary: str) -> str:
    """기사 원문 URL에서 본문을 추출하며, 실패 시 정제된 RSS 요약본을 반환합니다."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            extracted = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
            if extracted and len(extracted) > 200:
                return extracted[:1500]  # 속도 및 토큰 최적화를 위해 1,500자 제한
    except Exception as e:
        print(f"   [!] 본문 추출 실패 ({url}): {e}")

    clean_fallback = trafilatura.extract(fallback_summary) if fallback_summary else ""
    return clean_fallback or fallback_summary or "본문 내용 없음"


def collect_news() -> str:
    """
    seen_urls.json을 참조해 이미 수집한 기사는 100% 제외하고,
    최근 24시간(부족 시 72시간) 이내의 새로운 기사만 수집한 뒤 기록을 갱신합니다.
    """
    seen_urls = _load_seen_urls()
    now_iso = datetime.now(timezone.utc).isoformat()
    collected_items = []
    newly_collected_count = 0

    for feed_info in RSS_FEEDS:
        print(f"   [*] 수집 중: {feed_info['name']}...")
        feed = feedparser.parse(feed_info["url"])

        # 이미 수집한 URL을 먼저 제외한 미수집 후보군 추출
        unseen_entries = [
            entry
            for entry in feed.entries
            if entry.get("link") and entry.get("link") not in seen_urls
        ]

        # 1차 시도: 미수집 기사 중 최근 24시간 이내 글
        target_entries = [
            entry for entry in unseen_entries if _is_within_hours(entry, hours=24)
        ]

        # 2차 보완(Fallback): 24시간 내 새 글이 없으면 최근 72시간(주말 대응)으로 범위 확장
        if not target_entries:
            target_entries = [
                entry for entry in unseen_entries if _is_within_hours(entry, hours=72)
            ]

        if not target_entries:
            print("      -> 새로 추가된 미수집 기사가 없습니다.")
            continue

        for entry in target_entries[: feed_info["limit"]]:
            title = entry.get("title", "제목 없음")
            link = entry.get("link", "")
            rss_summary = entry.get("summary", entry.get("description", ""))

            print(f"      - {title[:45]}...")
            content = _fetch_article_content(link, rss_summary)

            item_text = (
                f"### [{feed_info['category']}] {title}\n"
                f"- 출처: {feed_info['name']}\n"
                f"- 링크: {link}\n"
                f"- 내용:\n{content}\n"
            )
            collected_items.append(item_text)

            # 수집 완료된 URL과 현재 시각을 기록
            seen_urls[link] = now_iso
            newly_collected_count += 1

    if not collected_items:
        raise RuntimeError("새로 수집할 미수집 기사가 없습니다.")

    # 수집이 정상 완료되었을 때만 파일에 기록 저장
    _save_seen_urls(seen_urls)
    print(f"   [✓] 신규 기사 {newly_collected_count}건 수집 완료 (누적 기록: {len(seen_urls)}건)")

    separator = "\n" + ("=" * 50) + "\n"
    return separator + separator.join(collected_items)
