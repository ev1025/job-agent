from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import storage
from google.genai import types

import vertexai
from vertexai.preview import rag
from vertexai.generative_models import GenerativeModel, Tool
from datetime import datetime

import json
import os
import uvicorn

# Pydantic 모델 정의 (JSON 페이로드를 받기 위해)
class QuestionRequest(BaseModel):
    question: str

# FastAPI 앱 생성
app = FastAPI()

PROJECT_ID = "job-agent-471006"
LOCATION = "us-east4"  # RAG corpus가 있는 지역과 일치
CORPUS_NAME = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/3458764513820540928"
MODEL_ID = "gemini-2.0-flash-001"
similarity_top_k = 10
vector_distance_threshold = 0.5

system_prompt = f"""
### **명령 (Instruction)**
당신은 사용자의 요청에 맞춰 최적의 채용 공고를 추천하는 전문 IT 커리어 컨설턴트입니다.
RAG 시스템을 통해 검색된 채용 공고 문서들을 바탕으로 아래 조건에 맞는 답변을 생성해주세요.

### **출력 조건 (Output Constraints)**
1.  검색된 공고 중 **사용자 질의와 관련성이 높은 공고**만 선정해주세요.
2.  선정한 공고들을 아래 **Markdown 테이블 형식**으로 요약해주세요.
3.  테이블 아래에, 각 공고를 **추천하는 이유**를 2~3 문장으로 간략하게 설명해주세요.

### **출력 형식 (Output Format)**
**추천 채용 공고**

| 회사명 | 채용 제목 | 경력 조건 | 마감일 | 채용공고 |
|---|---|---|---|---|
| [회사명] | [채용 제목] | [경력 조건] | [마감일] | [채용공고]([실제 URL 주소]) |
| [회사명] | [채용 제목] | [경력 조건] | [마감일] | [채용공고]([실제 URL 주소]) |

- **[회사명]:** [추천 이유 설명]
- **[회사명]:** [추천 이유 설명]
"""

def query_rebuilder(question: str, MODEL_ID=MODEL_ID):
    parsing_prompt = f"""
    당신은 채용 공고 검색 시스템의 쿼리 분석 전문가입니다.
    사용자의 질문을 분석하여, 검색 시스템이 즉시 사용할 수 있는 JSON을 생성해주세요.

    # 사용 가능한 필드 (structData keys):
    - deadline_date (YYYY-MM-DD 형식 또는 '상시채용', '채용시')
    - posted_date (YYYY-MM-DD 형식)
    - location (문자열, 예: "서울 송파구")
    - experience (문자열, 예: "신입", "경력 3년 이상")
    - employment_type (문자열, 예: "정규직", "계약직")
    - company (문자열)

    # 지침:
    1. 질문의 핵심 내용을 'keywords'로 추출합니다.
    2. 질문에 포함된 필터 조건을 분석하여 'filter_string'을 생성합니다.
    3. 'filter_string'은 SQL의 WHERE 절과 유사하며, 'AND'로 조건을 연결합니다.
    4. 오늘 날짜는 '{datetime.now().strftime('%Y-%m-%d')}'입니다. 이를 기준으로 '올해', 내일', '이번 주', '다음 주' 등을 계산하여 'deadline_date' 필터를 YYYY-MM-DD 형식으로 정확하게 만드세요.
    5. 필터링 조건이 없으면 'filter_string'은 빈 문자열("")로 두세요.
    6. '9월'과 같은 월 단위 질문은 해당 월의 1일부터 마지막 날까지의 범위로 해석합니다. 사용자가 '마감일'인지 '등록일'인지 명확히 언급하지 않으면, 문맥상 더 자연스러운 필드를 선택하세요.
    
    # 예시 1
    질문: "다음 주 월요일까지 마감되는 서울 지역 파이썬 신입 공고 찾아줘"
    JSON:
    {{
      "keywords": "파이썬 신입 공고",
      "filter_string": "location = \\"서울\\" AND experience = \\"신입\\" AND deadline_date <= \\"2025-09-22\\""
    }}

    # 예시 2
    질문: "RAG 관련 공고 그냥 다 보여줘"
    JSON:
    {{
      "keywords": "RAG",
      "filter_string": ""
    }}
    
    # 실제 질문
    질문: "{question}"
    JSON:
    """
    client = GenerativeModel(
        model_name=MODEL_ID,
        system_instruction=parsing_prompt
    )
    
    response = client.generate_content(
        contents=question
    )

    structured_query_str = response.text.strip().replace("```json", "").replace("```", "")
    structured_query = json.loads(structured_query_str)
    
    search_keywords = structured_query.get("keywords", question)
    final_filter_string = structured_query.get("filter_string", "")
    
    return search_keywords + final_filter_string

def vertex_init(PROJECT_ID=PROJECT_ID, LOCATION=LOCATION):
    vertexai.init(project=PROJECT_ID, location=LOCATION)

def rerank_model(question: str, CORPUS_NAME=CORPUS_NAME, MODEL_ID=MODEL_ID,
                 similarity_top_k=similarity_top_k, system_prompt=system_prompt):
    vertex_init()
    config = rag.RagRetrievalConfig(
        top_k=similarity_top_k,
        ranking=rag.Ranking(
            rank_service=rag.RankService(
                model_name="semantic-ranker-default@latest",
            )
        )
    )
    
    rag_retrieval_tool = Tool.from_retrieval(
        retrieval=rag.Retrieval(
            source=rag.VertexRagStore(
                rag_resources=[
                    rag.RagResource(
                        rag_corpus=CORPUS_NAME,
                    )
                ],
                rag_retrieval_config=config
            ),
        )
    )
    
    rag_model = GenerativeModel(
        model_name=MODEL_ID,
        tools=[rag_retrieval_tool],
        system_instruction=system_prompt
    )
    
    chat = rag_model.start_chat()
    
    pre_question = query_rebuilder(question)
    
    response = chat.send_message(pre_question)
    
    return response

# --- FastAPI 엔드포인트 추가 ---
@app.get("/")
def health_check():
    """상태 확인을 위한 엔드포인트"""
    return {"status": "healthy"}

@app.post("/ask")
def ask_question(request: dict):
    # dict에서 바로 값 꺼내기
    question = request.get("question")
    result = query_rebuilder(question)

    return result
    
    # # RAG 모델 호출
    # result = rerank_model(question)

    # return {"answer": result.text}
    # try:
    #     print(request.question)
    #     response = rerank_model(request.question)
    #     print(response)
        
    #     # 모델의 text 값을 추출하여 JSON 객체에 담아 반환
    #     assistant_response = response.text
    #     return {"answer": assistant_response}
        
    # except Exception as e:
    #     # 오류 발생 시 500 Internal Server Error 반환
    #     raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("rag_main:app", host="0.0.0.0", port=port, reload=False)