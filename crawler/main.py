import asyncio
import os
import json
from datetime import datetime, timedelta

from dotenv import load_dotenv
from google.cloud import storage
import vertexai
from vertexai import rag

from crawler.scrapers.saramin import crawl_saramin # 기존 크롤러 모듈

# --- 1. 전체 설정 ---
load_dotenv()

# 오늘 날짜를 기반으로 동적 이름 생성
today_date_str = datetime.now().strftime('%Y-%m-%d')

# GCP 및 Vertex AI 설정
PROJECT_ID = "job-agent-471006"
LOCATION = "us-east4"
CORPUS_DISPLAY_NAME = f"job_corpus_{today_date_str}"

# GCS 설정
GCS_BUCKET_NAME = "job-agent-raw-json"
GCS_DESTINATION_FOLDER = "rag-source-data"
GCS_FILENAME_PREFIX = f"job_{today_date_str}"
GCS_URI_FOR_RAG = f"gs://{GCS_BUCKET_NAME}/{GCS_DESTINATION_FOLDER}/"

# 크롤링 및 배치 설정
BATCH_SIZE = 500
TOTAL_PAGE_LIMIT = 1
SEARCH_KEYWORDS = ['청소']
# <<-- 이 부분이 누락되었습니다. 여기에 다시 추가했습니다.
SEARCH_START_DATE_STR = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# --- 2. GCS 업로드 헬퍼 함수 ---

def upload_batch_to_gcs(jobs_batch: list, file_index: int, bucket):
    """채용 공고 배치(list)를 GCS에 part 파일로 업로드합니다."""
    if not jobs_batch:
        return

    gcs_blob_name = f"{GCS_DESTINATION_FOLDER}/{GCS_FILENAME_PREFIX}_part_{file_index}.jsonl"
    blob = bucket.blob(gcs_blob_name)

    jsonl_records = []
    for job in jobs_batch:
        content = job.get('제목', '') + "\n\n" + job.get('상세내용', '')
        metadata = {k: v for k, v in job.items() if k not in ['rec_idx', '제목', '상세내용']}
        json_record = {
            "id": str(job.get('rec_idx')),
            "structData": metadata,
            "content": content
        }
        jsonl_records.append(json.dumps(json_record, ensure_ascii=False))

    final_jsonl_content = "\n".join(jsonl_records)

    try:
        blob.upload_from_string(final_jsonl_content, content_type="application/jsonl")
        print(f"✅ {len(jobs_batch)}개 공고를 {gcs_blob_name} 파일로 GCS에 업로드 완료.")
    except Exception as e:
        print(f"🚨 GCS 업로드 중 오류 발생 (파일: {gcs_blob_name}): {e}")

# --- 3. RAG Engine 로드 헬퍼 함수 ---

def ingest_gcs_files_to_rag(gcs_uri: str):
    """지정된 GCS 경로의 모든 파일을 RAG Engine으로 가져옵니다."""
    print("\n--- 2단계: RAG Engine으로 데이터 가져오기 시작 ---")
    
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    
    corpora = rag.list_corpora()
    corpus = next((c for c in corpora if c.display_name == CORPUS_DISPLAY_NAME), None)
    
    if not corpus:
        print(f"'{CORPUS_DISPLAY_NAME}' 코퍼스를 새로 생성합니다.")
        corpus = rag.create_corpus(display_name=CORPUS_DISPLAY_NAME)
    else:
        print(f"기존 코퍼스 '{CORPUS_DISPLAY_NAME}'를 사용합니다.")

    print(f"'{gcs_uri}' 경로의 파일들을 RAG Engine으로 가져옵니다.")
    try:
        rag.import_files(
            corpus.name,
            [gcs_uri],
        )
        print("✅ Storage -> VectorDB 임포트 작업이 성공적으로 시작되었습니다.")
        print("   (실제 인덱싱 완료까지는 데이터 양에 따라 시간이 소요될 수 있습니다)")
    except Exception as e:
        print(f"❗ RAG Engine 임포트 중 오류 발생: {e}")


# --- 4. 메인 실행 함수 ---

async def main():
    """크롤링, GCS 업로드, RAG Engine 임포트를 순차적으로 실행합니다."""
    start_time = datetime.now()

    # 1단계: 크롤링 및 GCS 배치 업로드
    print(f"--- 1단계: 크롤링 및 GCS 배치 업로드 시작 (파일명 접두사: {GCS_FILENAME_PREFIX}) ---")
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    
    all_jobs_buffer = []
    total_jobs_uploaded = 0
    file_index = 1
    
    # 여기서 사용할 시작 날짜 객체를 미리 생성합니다.
    start_date_obj = datetime.strptime(SEARCH_START_DATE_STR, "%Y-%m-%d")

    for keyword in SEARCH_KEYWORDS:
        print(f"\n> 키워드: '{keyword}' 크롤링 중...")
        async for jobs_from_page in crawl_saramin(start_date_obj, set(), TOTAL_PAGE_LIMIT, keyword):
            all_jobs_buffer.extend(jobs_from_page)
            
            if len(all_jobs_buffer) >= BATCH_SIZE:
                batch_to_upload = all_jobs_buffer[:BATCH_SIZE]
                all_jobs_buffer = all_jobs_buffer[BATCH_SIZE:]

                upload_batch_to_gcs(batch_to_upload, file_index, bucket)
                
                total_jobs_uploaded += len(batch_to_upload)
                file_index += 1

    if all_jobs_buffer:
        upload_batch_to_gcs(all_jobs_buffer, file_index, bucket)
        total_jobs_uploaded += len(all_jobs_buffer)
    
    print(f"\n--- 1단계 완료: 총 {total_jobs_uploaded}개 공고를 GCS에 저장했습니다. ---")

    if total_jobs_uploaded > 0:
        await asyncio.to_thread(ingest_gcs_files_to_rag, GCS_URI_FOR_RAG)
    else:
        print("\n--- 업로드된 데이터가 없어 RAG Engine 임포트를 건너뜁니다. ---")

    print(f"\n--- 모든 작업 완료 ---")
    print(f"총 소요 시간: {datetime.now() - start_time}")

if __name__ == "__main__":
    asyncio.run(main())