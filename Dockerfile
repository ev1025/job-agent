FROM python:3.10-slim

WORKDIR /app

# 시스템 패키지 설치 (MySQL + OCR)
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    gcc \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Tesseract 설치 확인
RUN tesseract --version

# numpy 먼저 설치하여 호환성 문제 방지
RUN pip install --no-cache-dir numpy==1.24.3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 사람인 크롤러 실행
CMD ["python", "-m", "crawler/main"]
