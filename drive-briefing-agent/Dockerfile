# uv가 사전 설치된 공식 Python 3.12 슬림 이미지 사용
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# 컨테이너 내부 시간대를 한국 시간(KST)으로 고정 (브리핑 문서 날짜 정확도 유지)
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 의존성 파일 먼저 복사 후 패키지 설치 (빌드 캐시 최적화)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 소스 코드 복사
COPY main.py ./
COPY src/ ./src/

# 컨테이너 실행 시 자동 수행할 명령어
CMD ["uv", "run", "--no-dev", "python", "main.py"]
