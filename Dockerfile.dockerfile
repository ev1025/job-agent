# 파이썬 3.10 공식 이미지를 기반으로 빌드
FROM python:3.10-slim

# 작업 디렉터리를 /app으로 설정
WORKDIR /app

# .env 파일과 requirements.txt를 복사
COPY .env .
COPY requirements.txt .

# 필요한 파이썬 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 전체를 컨테이너에 복사
COPY . .

# 종속성 파일들 제거 (컨테이너 이미지 크기 최적화)
RUN rm -f .env requirements.txt

# MySQL 클라이언트 라이브러리 설치
# aiomysql을 사용하는 데 필요함
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 컨테이너 실행 시 main.py를 실행하도록 설정
CMD ["python", "main.py"]