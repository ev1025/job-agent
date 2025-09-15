import streamlit as st
import requests
import json

# 🚀 이 부분을 본인의 Cloud Run API URL로 변경하세요!
API_URL = "https://rag-chatbot-941837367982.us-east4.run.app/ask"

# --- Streamlit UI 설정 ---
st.title("🤖 AI 채용 공고 챗봇")
st.caption("궁금한 채용 공고를 질문해보세요. (예: 다음 주 마감되는 LLM 신입 공고 찾아줘)")

# 대화 기록을 session_state에 저장
if "messages" not in st.session_state:
    st.session_state.messages = []

# 이전 대화 기록을 화면에 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 사용자 질문 입력 받기
if prompt := st.chat_input("질문을 입력하세요..."):
    # 사용자 메시지를 대화 기록에 추가하고 화면에 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # API에 보낼 대화 기록 (이제 API는 history를 사용하지 않음)
    # payload에서 history 필드 제거
    payload = {
        "question": prompt
    }

    # 로딩 스피너 표시
    with st.spinner('답변을 생성하는 중입니다...'):
        try:
            # API 서버에 POST 요청 보내기
            response = requests.post(API_URL, json=payload)
            response.raise_for_status() # 오류가 있으면 예외 발생

            # 답변 받아오기
            assistant_response = response.json().get("answer", "답변을 받아오지 못했습니다.")

            # AI 답변을 대화 기록에 추가하고 화면에 표시
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            with st.chat_message("assistant"):
                st.markdown(assistant_response)

        except requests.exceptions.RequestException as e:
            st.error(f"API 요청 중 오류가 발생했습니다: {e}")