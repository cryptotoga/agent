FROM python:3.11-slim

# 파이썬 로그가 버퍼링 없이 docker logs에 즉시 출력되도록 설정
ENV PYTHONUNBUFFERED=1

# 디스코드 음성 재생(FFmpeg) 및 음성 패킷 처리(libopus)에 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
