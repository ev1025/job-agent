# 1. 사용할 기본 이미지 설정
# 경량화된 Python 3.10 이미지 사용
FROM python:3.10-slim

# 2. 컨테이너 내부의 작업 디렉토리 설정
# 애플리케이션 코드가 위치할 디렉토리
WORKDIR /app

# 3. 필요한 시스템 패키지 설치
# MySQL 클라이언트 및 기타 의존성 설치.
# 이는 MySQL-python, mysqlclient 등과 같은 파이썬 라이브러리가
# C 컴파일러와 MySQL 헤더 파일을 필요로 하기 때문입니다.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 4. 파이썬 라이브러리 설치
# requirements.txt 파일을 복사하여 의존성을 먼저 설치합니다.
# 이는 Docker 레이어 캐싱을 활용하여 빌드 속도를 높이는 좋은 관행입니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 모든 애플리케이션 코드 복사
# requirements.txt를 제외한 나머지 모든 프로젝트 파일들을 컨테이너로 복사합니다.
# .dockerignore 파일을 사용해 불필요한 파일(e.g., .git, .env 등)을 제외하면 더 효율적입니다.
COPY . .

# 6. 컨테이너가 시작될 때 실행할 명령어 설정
# 프로젝트의 메인 스크립트(예: crawler/main.py)를 실행합니다.
CMD ["python", "crawler/main.py"]