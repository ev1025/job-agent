# 1. 사용할 기본 이미지 설정
FROM python:3.10-slim

# 2. 컨테이너 내부의 작업 디렉토리 설정
WORKDIR /app

# 3. 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. MySQL 클라이언트 및 기타 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 5. 모든 애플리케이션 코드 복사
# 현재 로컬 디렉토리의 모든 파일을 컨테이너의 /app으로 복사합니다.
COPY . .

# 6. 보안을 위해 .env 파일 제거
RUN rm -f .env

# 7. 컨테이너가 시작될 때 실행할 명령어 설정
# main.py는 crawler 폴더 안에 있으므로 경로를 지정해야 합니다.
CMD ["python", "crawler/main.py"]