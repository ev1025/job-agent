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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 사람인 크롤러 실행
CMD ["python", "-u", "crawler/main.py"]