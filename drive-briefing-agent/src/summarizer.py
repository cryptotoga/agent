import os
import time
from datetime import datetime
from google import genai
from google.genai import types

# 실제 API에서 검증된 모델 체인 + 충분한 타임아웃(120초)
MODEL_FALLBACK_CHAIN = [
    {"provider": "gemini", "model": "gemini-3.8-flash", "timeout": 120},
    {"provider": "gemini", "model": "gemini-3.6-flash", "timeout": 120},
    {"provider": "gemini", "model": "gemini-3.5-flash-lite", "timeout": 90},
    # 타사 무료/예비 API (키가 있을 때만 작동)
    {"provider": "gemini", "model": "gemini-3.1-flash-lite", "timeout": 90},
]


def _call_gemini(model_name: str, system_inst: str, prompt: str, timeout_sec: int) -> str:
    client = genai.Client(
        http_options=types.HttpOptions(timeout=timeout_sec * 1000)
    )
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_inst,
            temperature=0.4,
        ),
    )
    if not response.text:
        raise ValueError(f"{model_name}: 빈 응답 반환")
    return response.text


def _call_openai_compatible(
    model_name: str, system_inst: str, prompt: str, timeout_sec: int, api_key: str, base_url: str | None = None
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_sec)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_inst},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError(f"{model_name}: 빈 응답 반환")
    return content


def generate_insight_briefing(raw_news_text: str) -> str:
    today_str = datetime.now().strftime("%Y년 %m월 %d일")

    system_instruction = """
    당신은 실리콘밸리의 수석 테크 전략가이자 월스트리트의 거시경제 애널리스트입니다.
    제공된 오늘의 글로벌 테크 및 경제/금융 뉴스 원문을 바탕으로, 독자가 '세상이 어떻게 돌아가고 있으며 앞으로 어떻게 변할지' 깊은 통찰을 얻을 수 있는 심층 브리핑 문서를 한국어로 작성하세요.

    [작성 원칙]
    1. 단순 뉴스 나열이나 표면적 요약을 금지합니다. 서로 다른 분야(기술 트렌드 ↔ 금리/자본 이동 ↔ 지정학) 간의 연결 고리를 찾아 입체적으로 엮으세요.
    2. 이 문서는 추후 NotebookLM의 'AI 음성 개요(팟캐스트)'의 소스 문서로 투입됩니다. 두 명의 호스트가 깊이 있는 토론을 펼칠 수 있도록 논리적 인과관계와 구체적인 근거(수치, 기업명, 기술명)를 명확히 서술하세요.
    3. 반드시 아래의 마크다운 구조를 따르세요.

    [문서 구조]
    # 데일리 글로벌 테크 & 경제 인사이트 브리핑 ({오늘 날짜})

    ## 1. 오늘의 핵심 메가트렌드 (Executive Summary)
    - 오늘 수집된 기술과 경제 이슈를 관통하는 가장 큰 흐름 1~2가지를 3~4문장으로 압축

    ## 2. 심층 분석: 현상(What) → 원인(Why) → 파급 효과(So What)
    (가장 중요한 3~4개의 핵심 테마를 선정하여 각각 아래 3단계로 분석)
    ### 테마 1: [핵심 주제를 한 줄로 요약한 제목]
    - **무슨 일이 벌어졌나 (What):** 핵심 팩트와 관련 매체/수치 요약
    - **왜 이런 일이 일어났나 (Why):** 기술적 병목 해결, 자본의 이해관계, 거시경제적 배경 등 근본 원인 분석
    - **앞으로 어떻게 될 것인가 (So What):** 향후 6개월~2년 내 산업, 금융 시장, 한국 경제에 미칠 파급 효과 및 주목해야 할 관전 포인트

    ## 3. 호스트 토론용 핵심 질문 (Discussion Prompts)
    - 이 브리핑을 바탕으로 깊이 생각해 볼 만한 날카로운 질문 3가지
    """

    prompt = (
        f"오늘 날짜: {today_str}\n\n"
        f"다음은 오늘 수집된 원문 기사 데이터입니다:\n{raw_news_text}"
    )

    errors = []

    for candidate in MODEL_FALLBACK_CHAIN:
        provider = candidate["provider"]
        model_name = candidate["model"]
        timeout_sec = candidate["timeout"]

        key_map = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        api_key = os.getenv(key_map[provider])
        if not api_key:
            continue

        # 일시적 503 에러 대비 최대 2회 시도
        for attempt in range(1, 3):
            try:
                print(f"   [*] 모델 호출 시도 ({attempt}/2): {provider} / {model_name} (제한시간 {timeout_sec}초)...")
                if provider == "gemini":
                    return _call_gemini(model_name, system_instruction, prompt, timeout_sec)
                elif provider == "groq":
                    return _call_openai_compatible(
                        model_name,
                        system_instruction,
                        prompt,
                        timeout_sec,
                        api_key=api_key,
                        base_url="https://api.groq.com/openai/v1",
                    )
                elif provider == "openai":
                    return _call_openai_compatible(
                        model_name, system_instruction, prompt, timeout_sec, api_key=api_key
                    )

            except Exception as e:
                err_str = str(e)
                # 503 일시적 트래픽 과부하일 경우 4초 쉬고 1회 재시도
                if "503" in err_str and attempt == 1:
                    print("   [!] 서버 일시적 과부하(503). 4초 대기 후 재시도합니다...")
                    time.sleep(4)
                    continue

                err_msg = f"{provider}/{model_name} 실패: {e}"
                print(f"   [!] {err_msg} -> 다음 예비 모델로 전환합니다.")
                errors.append(err_msg)
                break

    raise RuntimeError("설정된 모든 LLM 모델 호출에 실패했습니다:\n" + "\n".join(errors))
