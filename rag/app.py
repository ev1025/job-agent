from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import uvicorn
from rag_service.rag import rerank_model

# Pydantic 모델 정의
class QuestionRequest(BaseModel):
    question: str

# FastAPI 앱 생성
app = FastAPI()

# --- FastAPI 엔드포인트 ---
@app.get("/")
def health_check():
    """상태 확인을 위한 엔드포인트"""
    return {"status": "healthy"}

@app.post("/ask")
def ask_question(request: QuestionRequest):
    """
    사용자 질문을 받아 답변을 생성하는 엔드포인트.
    """
    if not request.question:
        raise HTTPException(status_code=400, detail="Question not provided")

    try:
        # RAG 서비스 호출
        response = rerank_model(request.question)
        assistant_response = response.text
        return {"answer": assistant_response}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)