FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# 기본 패키지
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    build-essential \
    git \
    wget \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    libgl1 \
    libglib2.0-0 \
    libasound2 \
    libxfixes3 \
    libxi6 \
    libxrender1 \
    libxtst6 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxshmfence1 \
    fonts-liberation \
    libappindicator3-1 \
    curl \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# pip 업데이트
RUN python3 -m pip install --upgrade pip

WORKDIR /app

# requirements 먼저 복사 (docker cache 활용)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# playwright
RUN pip install playwright
RUN playwright install chromium

# 코드 복사
COPY . .

# worker 기반 실행
CMD ["gunicorn","main:app","-k","uvicorn.workers.UvicornWorker","-w","1","-b","0.0.0.0:8000","--timeout","600"]
