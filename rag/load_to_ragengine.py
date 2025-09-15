import vertexai
from vertexai import rag

# --- 설정 ---
PROJECT_ID = "job-agent-471006" # 본인 프로젝트 ID
LOCATION = "us-east4"
CORPUS_DISPLAY_NAME = "job-agent-corpus" # RAG 코퍼스 이름

# 2단계에서 출력된 GCS URI를 여기에 붙여넣으세요.
GCS_URI_TO_INGEST = "gs://job-agent-raw-json/rag-source-data/"

def load_data_to_rag_engine():
    """GCS의 파일들을 RAG Engine으로 가져옵니다."""
    
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    
    # RAG corpus 목록
    corpora = rag.list_corpora()
    corpus = next((c for c in corpora if c.display_name == CORPUS_DISPLAY_NAME), None)
    
    if not corpus:
        print(f"--- '{CORPUS_DISPLAY_NAME}' 코퍼스를 새로 생성합니다. ---")
        
        embedding_model_config = rag.RagEmbeddingModelConfig(
             publisher_model="publishers/google/models/text-embedding-004"
  )
        corpus = rag.create_corpus(
            display_name=CORPUS_DISPLAY_NAME,
            rag_embedding_model_config=embedding_model_config
        )
    else:
        print(f"--- 기존 코퍼스 '{CORPUS_DISPLAY_NAME}'를 사용합니다. ---")

    print(f"코퍼스 정보: {CORPUS_DISPLAY_NAME}")

    # GCS에서 파일 가져오기 및 자동 임베딩/인덱싱 시작
    print(f"--- '{GCS_URI_TO_INGEST}' 경로의 파일들을 RAG Engine으로 가져옵니다. ---")
    try:
        print("\n Storage -> VectorDB 작업이 시작되었습니다.")
        rag.import_files(
            corpus_name=corpus.name,
            paths = [GCS_URI_TO_INGEST], 
            # transformation_config=rag.TransformationConfig(
            # chunking_config=rag.ChunkingConfig(
            #     chunk_size=512,
            #     chunk_overlap=100,
            #     ),
            # ),
            # max_embedding_requests_per_min=1000,
        )
    except Exception as e:
        print(f"❗ 오류 발생: {e}")
        

if __name__ == "__main__":
    load_data_to_rag_engine()