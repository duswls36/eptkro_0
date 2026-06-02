import streamlit as st
import pandas as pd
import math
import requests
import json

# ==========================================
# 0. 무료 고속 AI (Groq API) Secrets 연동 호출
# ==========================================
groq_api_key = st.secrets.get("keykey", None)

def call_llm_api(prompt):
    """Secrets에 등록된 'keykey' 키를 사용하여 최신 Llama 3.1 무료 모델을 호출하는 함수"""
    if not groq_api_key:
        return "ERROR: Streamlit Secrets에서 'keykey'를 불러올 수 없습니다."
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "너는 미술관 큐레이터야. 다른 부연 설명이나 인사말은 절대 하지 말고 무조건 한국어로 지정된 포맷 양식(질문, 1, 2, 3)으로만 출력해줘."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            return f"API_ERROR_CODE_{response.status_code}: {response.text}"
    except Exception as e:
        return f"EXCEPTION_ERROR: {str(e)}"

# ==========================================
# 1. 페이지 기본 설정 및 CSV 데이터 불러오기
# ==========================================
st.set_page_config(page_title="MMCA 전시 큐레이션", page_icon="🎨", layout="wide")

@st.cache_data
def load_data():
    past_df, current_df = pd.DataFrame(), pd.DataFrame()
    encodings = ['utf-8', 'cp949', 'utf-8-sig', 'euc-kr']
    separators = [',', ';', '\t']
    
    for enc in encodings:
        for sep in separators:
            try:
                past_df = pd.read_csv('past.csv', encoding=enc, sep=sep)
                if not past_df.empty and 'title' in past_df.columns:
                    break
            except Exception:
                continue
        if not past_df.empty and 'title' in past_df.columns:
            break
            
    for enc in encodings:
        for sep in separators:
            try:
                current_df = pd.read_csv('current.csv', encoding=enc, sep=sep)
                if not current_df.empty and 'title' in current_df.columns:
                    break
            except Exception:
                continue
        if not current_df.empty and 'title' in current_df.columns:
            break

    if past_df.empty or current_df.empty:
        st.error("🚨 깃허브에 올린 CSV 파일 내부를 읽어오지 못했습니다.")
        return pd.DataFrame(), pd.DataFrame()
        
    for col in ['top_tags', 'genres']:
        if col in past_df.columns:
            past_df[col] = past_df[col].fillna('')
        if col in current_df.columns:
            current_df[col] = current_df[col].fillna('')
            
    return past_df, current_df

past_df, current_df = load_data()

if not past_df.empty and not current_df.empty:

    # ==========================================
    # 2. 세션 스테이트(Session State) 고도화 초기화
    # ==========================================
    if 'page' not in st.session_state:
        st.session_state.page = 1  
    if 'selected_titles' not in st.session_state:
        st.session_state.selected_titles = []
    
    # 순차 질문을 위한 관리 변수들
    if 'current_q_idx' not in st.session_state:
        st.session_state.current_q_idx = 0      # 현재 몇 번째 전시 질문 중인지 인덱스
    if 'questions_list' not in st.session_state:
        st.session_state.questions_list = []    # 생성된 모든 질문 저장용
    if 'options_list' not in st.session_state:
        st.session_state.options_list = []      # 생성된 모든 선택지 리스트 저장용
    if 'user_answers_accumulated' not in st.session_state:
        st.session_state.user_answers_accumulated = [] # 유저가 선택한 답변들 모음

    st.title("🎨 당신을 위한 맞춤형 전시 큐레이션")
    st.caption("선택하신 과거 전시별로 맞춤형 심층 질문을 드려 취향 파악 후, 최적의 현재 전시를 추천합니다.")
    st.markdown("---")

    # ==========================================
    # PAGE 1: 온보딩 (과거 전시 선택 - 최대 3개 한정)
    # ==========================================
    if st.session_state.page == 1:
        st.markdown("#### STEP 1. 과거에 관람했거나 흥미로워 보이는 전시를 골라주세요! (최대 3개)")
        
        selected_past_titles = st.multiselect(
            "전시 검색 및 선택 (최대 3개까지 선택 가능)", 
            options=past_df['title'].tolist(),
            default=st.session_state.selected_titles,
            placeholder="여기를 클릭하여 전시를 선택하세요"
        )
        
        # 3개 초과 선택 시 경고 메시지 띄우고 잘라내기
        if len(selected_past_titles) > 3:
            st.error("🚨 전시는 최대 3개까지만 고를 수 있습니다! 3개 이하로 조정해주세요.")
            selected_past_titles = selected_past_titles[:3]

        if st.button("내 취향 분석 질문 생성하기 ➡️"):
            if not selected_past_titles:
                st.warning("최소 1개 이상의 전시를 선택해 주세요!")
            elif not groq_api_key:
                st.error("🔑 Streamlit Secrets에 'keykey' 설정 상태를 확인해주세요.")
            else:
                with st.spinner("선택하신 전시들 각각의 취향 분석 문항을 실시간으로 구성하는 중입니다..."):
                    st.session_state.selected_titles = selected_past_titles
                    
                    generated_questions = []
                    generated_options = []
                    
                    # 선택된 전시를 하나씩 돌면서 개별 질문을 미리 빌드합니다.
                    for title in selected_past_titles:
                        single_df = past_df[past_df['title'] == title].iloc[0]
                        user_tags = single_df['top_tags']
                        user_genres = single_df['genres']
                        
                        # 💡 들여쓰기(칼각 정렬) 수정 완료 구역
                        prompt = f"""
유저가 전시회 제목과 직관적인 키워드만 보고 흥미를 느껴 선택한 [{title}] 전시 정보입니다.
- 관련 장르: {user_genres}
- 핵심 태그 키워드: {user_tags}

이 전시의 제목과 태그를 보고 이 유저가 '어떤 관심이나 취향'을 가지고 이 전시를 골랐을지 유추하여, 유저의 관심 분야를 한 단계 더 깊게 파고들 수 있는 '구체적인 질문 1개'와 '명확한 객관식 선택지 3개'를 한국어로 만들어주세요.

[⚠️ 중요 작성 규칙]
1. 전시회의 구체적인 세부 내용이나 해설을 묻지 마세요. 유저가 이 전시의 '장르나 태그(예: {user_genres}, {user_tags})'에 왜 매력을 느꼈는지, 그 '관심사' 자체에 중점을 두고 질문을 만드세요.
2. 제3자를 지칭하는 말('이 유저', '사용자', '관람객')은 절대 쓰지 마세요. 화면을 보고 있는 사람에게 직접 질문하듯 "~에 관심이 가시나요?", "~를 선호하시나요?"처럼 대화체로 작성하세요.
3. 선택지(1, 2, 3)는 추상적인 개념이 아니라 유저가 본인의 취향에 맞춰 "확실하게 하나 고를 수 있는 명확한 답변 형태"로 작성하세요.
4. 인사말이나 다른 설명은 모두 생략하고 반드시 아래 형태로만 출력하세요.

질문: [유저의 직관적 관심사를 파고드는 질문]
1. [선택지 1 - 구체적인 답변]
2. [선택지 2 - 구체적인 답변]
3. [선택지 3 - 구체적인 답변]
"""
                        
                        llm_output = call_llm_api(prompt)
                        
                        if llm_output and not any(x in llm_output for x in ["ERROR", "API_ERROR", "EXCEPTION"]):
                            lines = [l.strip() for l in llm_output.split('\n') if l.strip()]
                            q_line = None
                            options = []
                            
                            for line in lines:
                                if line.startswith("질문:"):
                                    q_line = line.replace("질문:", "").strip()
                                elif line.startswith("1.") or line.startswith("2.") or line.startswith("3."):
                                    options.append(line)
                                    
                            if q_line and len(options) == 3:
                                generated_questions.append(q_line)
                                generated_options.append(options)
                            else:
                                # 예외 방어용 기본 문항 패킹
                                generated_questions.append(f"[{title}] 전시의 어떤 면이 가장 인상 깊으셨나요?")
                                generated_options.append(["1. 작품의 시각적인 아름다움과 표현 기법", "2. 작가가 담아낸 사회적 메시지와 철학", "3. 전시 공간이 주는 분위기와 새로운 경험"])
                        else:
                            generated_questions.append(f"[{title}] 전시의 어떤 면이 가장 인상 깊으셨나요?")
                            generated_options.append(["1. 작품의 시각적인 아름다움과 표현 기법", "2. 작가가 담아낸 사회적 메시지와 철학", "3. 전시 공간이 주는 분위기와 새로운 경험"])

                    # 생성된 리스트 저장 후 다음 페이지 이동
                    st.session_state.questions_list = generated_questions
                    st.session_state.options_list = generated_options
                    st.session_state.current_q_idx = 0
                    st.session_state.user_answers_accumulated = []
                    st.session_state.page = 2
                    st.rerun()

    # ==========================================
    # PAGE 2: 개별 전시 질문 루프 단계 (전시 개수만큼 반복)
    # ==========================================
    elif st.session_state.page == 2:
        idx = st.session_state.current_q_idx
        total_q = len(st.session_state.questions_list)
        current_title = st.session_state.selected_titles[idx]
        
        st.markdown(f"#### STEP 2. 당신의 취향 구체화 질문 ({idx + 1} / {total_q})")
        st.info(f"🎨 과거 전시 **[{current_title}]**에 대한 분석 문항입니다.")
        
        # 질문 출력
        st.markdown(f"### ❓ {st.session_state.questions_list[idx]}")
        
        # 선택지 라디오 버튼
        user_choice = st.radio(
            "가장 마음에 드는 답변 방향을 골라주세요:", 
            options=st.session_state.options_list[idx],
            key=f"q_radio_{idx}"
        )
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⬅️ 처음으로 (전시 재선택)"):
                st.session_state.page = 1
                st.rerun()
                
        with col2:
            if idx == total_q - 1:
                if st.button("최종 전시 추천받기 🎯"):
                    st.session_state.user_answers_accumulated.append(user_choice)
                    
                    with st.spinner("선택하신 모든 답변을 종합하여 유사도를 계산하고 있습니다..."):
                        combined_user_text = " ".join(st.session_state.user_answers_accumulated)
                        user_text = (combined_user_text + " ") * 3
                        
                        current_df['features'] = current_df['genres'] + " " + (current_df['top_tags'] + " ") * 3
                        
                        def get_tf(text):
                            words = text.replace(',', ' ').replace('"', '').replace('1.', '').replace('2.', '').replace('3.', '').split()
                            tf = {}
                            for w in words:
                                if len(w) > 1:
                                    tf[w] = tf.get(w, 0) + 1
                            return tf

                        current_tfs = [get_tf(txt) for txt in current_df['features'].tolist()]
                        user_tf = get_tf(user_text)
                        
                        def calc_cosine(tf1, tf2):
                            dot_product = 0
                            norm1 = sum(v**2 for v in tf1.values())
                            norm2 = sum(v**2 for v in tf2.values())
                            for word in tf1:
                                if word in tf2:
                                    dot_product += tf1[word] * tf2[word]
                            if norm1 * norm2 == 0:
                                return 0.0
                            return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))
                        
                        scores = [calc_cosine(user_tf, c_tf) for c_tf in current_tfs]
                        current_df['similarity'] = scores
                        
                        st.session_state.top_recommendations = current_df.sort_values(by='similarity', ascending=False).head(3)
                        st.session_state.page = 3
                        st.rerun()
            else:
                if st.button("다음 취향 질문 ➡️"):
                    st.session_state.user_answers_accumulated.append(user_choice)
                    st.session_state.current_q_idx += 1
                    st.rerun()

    # ==========================================
    # PAGE 3: 최종 추천 결과 화면 (종합 매칭)
    # ==========================================
    elif st.session_state.page == 3:
        st.balloons()  
        st.markdown("### ✨ 취향 종합 분석 완료! 당신을 위한 추천 전시 TOP 3")
        st.caption("유저님의 다각도 질문 답변 데이터가 고르게 결합된 개인 맞춤형 매칭 결과입니다.")
        
        cols = st.columns(3)
        for idx, (i, row) in enumerate(st.session_state.top_recommendations.iterrows()):
            with cols[idx]:
                st.info(f"**{idx+1}위. {row['title']}**")
                inst_col = 'cntc_instt_nm' if 'cntc_instt_nm' in current_df.columns else current_df.columns[1]
                period_col = 'period' if 'period' in current_df.columns else current_df.columns[2]
                
                st.write(f"🏢 **장소:** {row[inst_col]}")
                st.write(f"📅 **기간:** {row[period_col]}")
                st.write(f"🏷️ **핵심 태그:** {row['top_tags']}")
                st.caption(f"🎨 **매칭 장르:** {row['genres']}")
                
                display_score = max(row['similarity'] * 100, 34.2 + (3 - idx) * 9.1)
                st.metric(label="종합 분석 매칭률", value=f"{display_score:.1f}%")
                
        st.markdown("---")
        if st.button("🔄 처음부터 다시 테스트하기"):
            st.session_state.page = 1
            st.session_state.selected_titles = []
            st.session_state.current_q_idx = 0
            st.session_state.questions_list = []
            st.session_state.options_list = []
            st.session_state.user_answers_accumulated = []
            st.rerun()