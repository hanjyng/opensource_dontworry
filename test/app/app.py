import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import yfinance as yf
import google.generativeai as genai
import json
from PIL import Image

from modules.sqlite3_db import init_db, save_expense, load_expenses
from modules.llm_gemini import analyze_receipt
from modules.exchange import get_exchange_rate


# 1. 페이지 설정
st.set_page_config(page_title="AI 여행 가계부", layout="wide")
st.title("Don't ₩orry | ✈️ AI 스마트 여행 가계부 (SQLite 연동)")

print(__name__)

# 앱 시작 시 DB 초기화 실행 (파일이 없으면 생성됨)
init_db()

# ==========================================
# 세션 상태 관리 (AI 폼 채우기용만 남김)
# ==========================================
# 'expenses' 리스트는 이제 DB가 대신하므로 삭제했습니다.
if 'form_date' not in st.session_state:
    st.session_state.form_date = datetime.today()
if 'form_store' not in st.session_state:
    st.session_state.form_store = ""
if 'form_category' not in st.session_state:
    st.session_state.form_category = "식비"
if 'form_price' not in st.session_state:
    st.session_state.form_price = 0.0

# ==========================================
# 2. 사이드바 설정
# ==========================================
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input(
        "Google Gemini API Key", 
        type="password",
        help="Google AI Studio에서 발급받은 키를 입력하세요.")
    st.divider()
    selected_date = st.date_input("여행 기준 날짜", datetime.today())
    currency = st.selectbox("현지 통화", ["USD", "JPY", "EUR", "CNY", "GBP", "VND"])
    
    with st.spinner(f'{selected_date} 기준 환율 조회 중...'):
        current_rate = get_exchange_rate(currency, selected_date)
    
    if current_rate:
        display_rate = current_rate * 100 if currency in ["JPY", "VND"] else current_rate
        unit = 100 if currency in ["JPY", "VND"] else 1
        st.metric(label=f"환율 ({unit} {currency})", value=f"{display_rate:.2f} KRW")
    else:
        current_rate = 1000.0
        st.warning("환율 조회 실패 (기본값 1000)")

# ==========================================
# 3. 메인: 영수증 입력 및 저장
# ==========================================
st.subheader("🧾 지출 기록하기")

col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader("영수증 업로드", type=['jpg', 'png', 'jpeg'])
    if uploaded_file:
        # PIL 이미지로 변환
        image = Image.open(uploaded_file)
        st.image(image, caption='이미지 미리보기', use_container_width=True)

with col2:
    # API 키가 없으면 분석 버튼 비활성화
    if not api_key:
        st.warning("👈 사이드바에 Gemini API Key를 먼저 입력해주세요.")
    
    # 분석 버튼
    if uploaded_file and api_key and st.button("🤖 AI 영수증 분석 실행"):
        with st.spinner('Gemini가 영수증을 읽고 있습니다...'):
            analyzed_data = analyze_receipt(image, api_key)
            
            if analyzed_data:
                # 분석 성공 시, 세션 상태 업데이트 (폼에 자동 채우기 위해)
                try:
                    st.session_state.form_date = datetime.strptime(analyzed_data.get('date', str(selected_date)), "%Y-%m-%d")
                except:
                    st.session_state.form_date = selected_date
                
                st.session_state.form_store = analyzed_data.get('store_name', '')
                st.session_state.form_category = analyzed_data.get('category', '기타')
                st.session_state.form_price = float(analyzed_data.get('price', 0.0))
                
                st.success("분석 완료!")

    # -------------------------------------------------------
    # 입력 폼 (AI 분석 결과가 value로 들어감)
    # -------------------------------------------------------
    with st.form("expense_form"):
        # value 파라미터에 st.session_state 값을 연결하여 자동 채움 구현
        input_date = st.date_input("날짜", value=st.session_state.form_date)
        input_store = st.text_input("가게명", value=st.session_state.form_store)
        
        # 카테고리 인덱스 찾기
        options = ["식비", "쇼핑", "관광", "교통", "숙박", "기타"]
        try:
            cat_index = options.index(st.session_state.form_category)
        except:
            cat_index = 5  # 기타
            
        input_category = st.selectbox("카테고리", options, index=cat_index)
        input_price = st.number_input(
            f"금액 ({currency})", 
            min_value=0.0, 
            format="%.2f", 
            value=st.session_state.form_price)
        
        submitted = st.form_submit_button("💾 지출 등록하기")
        
        if submitted:
            price_krw = input_price * current_rate
            # [변경] session_state 대신 DB 저장 함수 호출
            save_expense(
                input_date.strftime("%Y-%m-%d"),
                input_store,
                input_category,
                input_price,
                currency,
                int(price_krw),
                current_rate
            )
            st.success("데이터베이스에 안전하게 저장되었습니다!")
            # 폼 초기화 (선택 사항)
            st.session_state.form_store = ""
            st.session_state.form_price = 0.0

# ==========================================
# 4. 데이터 시각화 (DB 연동)
# ==========================================
st.divider()
st.subheader("📊 통계 및 내역 (DB 데이터)")

# [변경] DB에서 데이터 불러오기
df = load_expenses()

if not df.empty:
    # 컬럼 이름이 영어(DB) -> 한글(화면용) 매핑이 필요하면 rename 사용
    display_df = df.rename(columns={
        'date': '날짜',
        'store_name': '가게명',
        'category': '카테고리',
        'price_foreign': '현지 금액',
        'currency': '통화',
        'price_krw': '환산금액(KRW)',
        'exchange_rate': '적용환율'
    })

    c1, c2 = st.columns(2)
    with c1:
        # groupby 자동 처리를 위해 plotly가 편리함
        fig_bar = px.bar(
            display_df, 
            x="날짜", 
            y="환산금액(KRW)", 
            color="카테고리", 
            title="일자별/카테고리별 지출")
        st.plotly_chart(fig_bar, use_container_width=True)
    with c2:
        fig_pie = px.pie(display_df, values="환산금액(KRW)", names="카테고리", title="카테고리별 비중")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.dataframe(display_df, use_container_width=True)
    
    # CSV 다운로드 기능 (DB 데이터를 기반으로 생성)
    csv = display_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("CSV 다운로드", csv, "travel_log_db.csv", "text/csv")

else:
    st.info("아직 저장된 지출 내역이 없습니다.")