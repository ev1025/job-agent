FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# streamlit_app.py와 .streamlit 폴더를 함께 복사
COPY streamlit_app.py .
COPY .streamlit/ .streamlit/

EXPOSE 8080
# CMD를 간단하게 변경 (config.toml이 설정을 자동으로 적용)
CMD ["streamlit", "run", "streamlit_app.py"]