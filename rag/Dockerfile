# 베이스 이미지
FROM python:3.10-slim

# 작업 폴더 설정
WORKDIR /app

# requirements.txt 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI 애플리케이션 파일과 rag_service 디렉토리 복사
COPY app.py .
COPY rag_service/ rag_service/

# Cloud Run에서 포트는 환경변수 PORT를 사용 (빌드 시점에는 고정값 사용)
EXPOSE 8080

# uvicorn 실행 (환경변수 PORT 사용, 0.0.0.0 바인딩 필수)
CMD ["python", "app.py"]