# 🤖 AI 채용 공고 추천 챗봇 (Job Agent)

**AI 채용 공고 추천 챗봇**은 최신 채용 정보를 기반으로 사용자의 질문에 가장 적합한 공고를 찾아 추천하는 RAG(Retrieval-Augmented Generation) 시스템입니다.

매일 아침 자동으로 최신 채용 공고를 수집하고, 이미지로 된 공고 내용까지 OCR 기술로 빠짐없이 분석합니다. 사용자가 "다음 주에 마감되는 RAG 신입 공고 찾아줘"와 같이 자연어로 질문하면, Gemini AI가 질문의 의도를 파악하여 가장 관련성 높은 공고를 찾아 표 형태로 깔끔하게 정리해 줍니다.
<br><br>
## 🔀 프로젝트 흐름도
<img width="1841" height="303" alt="image" src="https://github.com/user-attachments/assets/154c7710-5087-4773-a165-c993770b8720" />

<br><br>

## ⚙️ 시스템 아키텍처
1.  **⏰ 자동화된 데이터 수집 (Google Cloud Scheduler):** 매일 오전 7시, 스케줄러가 데이터 수집 파이프라인(`main.py`)을 트리거합니다.
2.  **🕸️ 웹 크롤링 & OCR (Cloud Run):** `saramin.py` 크롤러가 '사람인' 사이트에서 최신 채용 공고를 수집합니다. 공고 본문이 이미지일 경우, `ocr.py`가 **Vision API**를 통해 텍스트를 추출합니다.
3.  **📦 데이터 저장 (Google Cloud Storage):** 수집된 데이터는 RAG Engine이 인식할 수 있는 JSONL 형식으로 변환되어 GCS 버킷에 저장됩니다.
4.  **🧠 벡터 인덱싱 (Vertex AI RAG Engine):** GCS에 저장된 파일들을 **RAG Engine**으로 임포트하여, AI가 빠르게 검색할 수 있도록 벡터 데이터로 변환하고 인덱싱합니다. (이 과정에서 DB가 최신 상태로 업데이트됩니다.)
5.  **💬 사용자 인터페이스 (Streamlit):** 사용자는 `streamlit_app.py`로 만들어진 웹 UI를 통해 챗봇과 대화합니다.
6.  **FastAPI 백엔드 (Cloud Run):** Streamlit 앱은 사용자의 질문을 `app.py`로 구현된 FastAPI 서버에 전달합니다.
7.  **🔍 지능형 쿼리 분석 (Gemini Flash - 1차):** `rag.py`의 `query_rebuilder` 함수가 사용자의 자연어 질문("서울 지역 신입 공고")을 RAG Engine이 이해할 수 있는 구조화된 필터(`location = "서울" AND experience = "신입"`)로 변환합니다. (1차 프롬프트 엔지니어링)
8.  **✅ 검색 및 재랭킹 (RAG Engine):** 변환된 쿼리를 사용해 RAG Engine에서 가장 관련성 높은 공고 문서를 검색하고, **Semantic Ranker**를 통해 정확도를 높입니다.
9.  **📝 최종 답변 생성 (Gemini Flash - 2차):** 검색된 공고 데이터와 시스템 프롬프트를 **Gemini Flash** 모델에 전달하여, 사용자가 보기 좋은 Markdown 테이블 형식의 최종 답변을 생성합니다. (2차 프롬프트 엔지니어링)
10. **📤 답변 전송:** 생성된 답변은 FastAPI를 거쳐 Streamlit UI에 표시됩니다.

<br><br>

## ✨ 주요 기능

  * **자동화된 데이터 파이프라인:** Google Cloud Scheduler를 통해 매일 자동으로 최신 채용 공고를 수집, 처리, 인덱싱합니다.
  * **지능형 자연어 검색:** Gemini 모델을 활용해 "다음 주 월요일까지 마감"과 같은 복잡한 자연어 질문을 정확한 날짜 필터로 변환하여 검색합니다.
  * **OCR 기반 텍스트 추출:** 공고 본문이 이미지로 되어 있어도 Google Vision API를 통해 텍스트를 정확히 추출하여 검색 대상에 포함시킵니다.
  * **의미 기반 재랭킹:** Vertex AI Semantic Ranker를 사용하여 검색 결과의 정확도를 극대화합니다.
  * **직관적인 챗봇 UI:** Streamlit을 사용하여 누구나 쉽게 질문하고 답변을 확인할 수 있는 인터페이스를 제공합니다.
  * **확장 가능한 서버리스 아키텍처:** FastAPI와 Cloud Run을 기반으로 하여 트래픽에 따라 유연하게 확장 가능합니다.

<br><br>

## 🛠️ 기술 스택

| 구분              | 기술                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| **Cloud** | **Google Cloud Platform (GCP)** |
| **AI / ML** | **Vertex AI RAG Engine**, **Gemini 2.0 Flash**, **Google Cloud Vision API (OCR)**, Semantic Ranker |
| **Data Storage** | **Google Cloud Storage**, **Google Cloud SQL** |
| **Backend** | Python, FastAPI, Uvicorn                                                                          |
| **Frontend** | Streamlit                                                                                         |
| **Crawling** | BeautifulSoup, httpx, asyncio                                                                     |
| **Orchestration** | **Google Cloud Scheduler** |
| **Deployment** | Docker, **Google Cloud Run** |

<br><br>
## 🚀 설치 및 실행 방법

### **사전 준비**

1.  Google Cloud Platform 프로젝트 생성 및 `gcloud` CLI 설치/인증
2.  Python 3.10+ 설치

### **1. 프로젝트 설정**

```bash
# 1. 레포지토리 클론
git clone https://github.com/ev1025/job-agent.git
cd job-agent

# 2. 파이썬 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 필요한 라이브러리 설치
pip install -r requirements.txt

# 4. 환경 변수 설정
# .env.example 파일을 복사하여 .env 파일을 만들고,
# 본인의 GCP 프로젝트 ID, GCS 버킷 이름 등을 입력합니다.
cp .env.example .env
```

### **2. 데이터 파이프라인 실행 (최초 1회)**

아래 명령어를 실행하여 채용 공고를 수집하고 RAG Engine에 데이터를 채웁니다.

```bash
python main.py
```

> 💡 **참고:** 이 작업은 Google Cloud Scheduler에 등록하여 매일 자동으로 실행되도록 설정할 수 있습니다.

### **3. API 서버 및 UI 실행**

```bash
# 1. (터미널 1) FastAPI 백엔드 서버 실행
uvicorn app:app --host 0.0.0.0 --port 8080

# 2. (터미널 2) Streamlit 프론트엔드 앱 실행
# streamlit_app.py 파일의 API_URL을 위에서 실행한 주소(또는 Cloud Run 배포 주소)로 수정해야 합니다.
streamlit run streamlit_app.py
```

이제 웹 브라우저에서 Streamlit 앱 주소(`http://localhost:8501`)로 접속하여 챗봇을 사용할 수 있습니다.
