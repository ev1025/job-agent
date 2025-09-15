import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
import json
from google.cloud import storage

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 1. DB 및 GCS 설정 ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
GCS_BUCKET_NAME = "job-agent-raw-json"
GCS_DESTINATION_FOLDER = "rag-source-data" # 파일을 저장할 GCS 폴더

# --- 2. 분할 설정 ---
LINES_PER_FILE = 2500  # 파일당 최대 라인 수 (10MB를 넘지 않도록 조절)

def process_and_upload_in_chunks():
    """DB 데이터를 여러 개의 작은 JSONL 파일로 분할하여 GCS에 직접 업로드합니다."""
    
    print("--- 1. 데이터베이스 연결 및 전체 데이터 추출 ---")
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)
    query = "SELECT rec_idx, title, company, description, location, experience, employment_type, posted_date, deadline_date, link FROM job_raw WHERE description IS NOT NULL AND description != ''"
    df = pd.read_sql(query, engine)
    df = df.where(pd.notnull(df), None)
    print(f"✅ 총 {len(df)}개의 데이터를 DB에서 가져왔습니다.")

    print(f"--- 2. GCS 버킷 '{GCS_BUCKET_NAME}'으로 분할 업로드 시작 ---")
    
    storage_client = storage.Client(project=os.getenv("PROJECT_ID"))
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    
    file_index = 1
    line_count = 0
    
    # 첫 번째 파일을 엽니다.
    gcs_blob_name = f"{GCS_DESTINATION_FOLDER}/job_data_part_{file_index}.jsonl"
    blob = bucket.blob(gcs_blob_name)
    f = blob.open("w", encoding="utf-8")

    for index, row in df.iterrows():
        # 설정한 라인 수를 초과하면, 현재 파일을 닫고 새 파일을 엽니다.
        if line_count >= LINES_PER_FILE:
            f.close() # 현재 파일 스트림을 닫아 업로드를 완료합니다.
            print(f"✅ {gcs_blob_name} 업로드 완료.")
            
            file_index += 1
            line_count = 0
            gcs_blob_name = f"{GCS_DESTINATION_FOLDER}/job_data_part_{file_index}.jsonl"
            blob = bucket.blob(gcs_blob_name)
            f = blob.open("w", encoding="utf-8")

        # JSONL 레코드 생성 및 파일에 쓰기
        content = row['title'] + "\n\n" + row['description']
        metadata = {k: v for k, v in row.items() if k not in ['rec_idx', 'description']}
        json_record = {"id": str(row['rec_idx']), "structData": metadata, "content": content, }
        f.write(json.dumps(json_record, ensure_ascii=False) + "\n")
        line_count += 1
        
    # 마지막 파일 닫기
    f.close()
    print(f"✅ {gcs_blob_name} 업로드 완료.")
    print(f"\n총 {file_index}개의 파일로 분할하여 업로드를 완료했습니다.")

if __name__ == "__main__":
    process_and_upload_in_chunks()