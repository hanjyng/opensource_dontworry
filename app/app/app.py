import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta  # [수정] timedelta 추가됨
import yfinance as yf
import google.generativeai as genai
import json
from PIL import Image

# 1. 페이지 설정
st.set_page_config(page_title="AI 여행 가계부", layout="wide")
st.title("✈️ AI 스마트 여행 가계부 (Gemini 연동)")

# 세션 상태 초기화 (데이터 저장 및 폼 자동 채우기용)
if 'expenses' not in st.session_state:
    st.session_state.expenses = []

# AI 분석 결과를 폼에 채워넣기 위한 세션 변수들
if 'form_date' not in st.session_state:
    st.session_state.form_date = datetime.today()
if 'form_store' not in st.session_state:
    st.session_state.form_store = ""
if 'form_category' not in st.session_state:
    st.session_state.form_category = "식비"
if 'form_price' not in st.session_state:
    st.session_state.form_price = 0.0

# ==========================================
# [기능] Gemini AI로 영수증 분석 함수
# ==========================================
def analyze_receipt(image, api_key):
    """
    Gemini 1.5 Flash 모델을 사용하여 영수증 이미지에서 정보를 추출합니다.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 프롬프트: AI에게 내리는 지시사항
        prompt = """
        Analyze this receipt image and extract the following information in JSON format:
        1. date (format: YYYY-MM-DD, if not found use today)
        2. store_name (name of the shop or restaurant)
        3. price (total amount, number only, no currency symbol)
        4. category (Choose one strictly from: 식비, 쇼핑, 관광, 교통, 숙박, 기타)

        Return ONLY the JSON string. Do not use Markdown code blocks.
        Example: {"date": "2024-01-01", "store_name": "Starbucks", "price": 15.50, "category": "식비"}
        """
        
        # 이미지와 프롬프트를 함께 전송
        response = model.generate_content([prompt, image])
        
        # 응답 텍스트에서 JSON 추출 (가끔 ```json ... ``` 이렇게 줄 때가 있어서 처리)
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        
        return data
        
    except Exception as e:
        st.error(f"AI 분석 중 오류가 발생했습니다: {e}")
        return None

# ==========================================
# [기능] 날짜별 환율 가져오기 (똑똑한 버전)
# ==========================================
@st.cache_data(ttl=3600)
def get_exchange_rate(target_currency, target_date=None):
    """
    선택한 날짜의 환율(종가)을 가져옵니다.
    주말이라 데이터가 없으면, 그 전 가장 최근 데이터를 가져옵니다.
    """
    if target_currency == "KRW":
        return 1.0
        
    ticker_symbol = f"{target_currency}KRW=X"
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # 날짜가 지정되지 않았거나 오늘이면 -> 실시간 데이터
        if target_date is None or target_date >= datetime.today().date():
            data = ticker.history(period="1d")
        else:
            # 과거 날짜인 경우: 해당 날짜 포함 일주일 전부터 데이터를 가져옴 (주말 대비)
            # end 날짜는 포함되지 않으므로 하루 더해줌
            start_date = target_date - timedelta(days=7)
            end_date = target_date + timedelta(days=1)
            data = ticker.history(start=start_date, end=end_date)

        if not data.empty:
            # 기간 중 가장 마지막 데이터(해당 날짜 혹은 직전 평일)의 종가(Close) 선택
            rate = data['Close'].iloc[-1]
            return round(rate, 2)
        else:
            return None
            
    except Exception as e:
        print(f"환율 조회 실패: {e}") # 터미널에 로그 남김
        return None
# ==========================================
# 2. 사이드바: 설정 및 API 키
# ==========================================
with st.sidebar:
    st.header("⚙️ 설정")
    
    # API 키 입력 (비밀번호처럼 가려서 입력)
    api_key = st.text_input("Google Gemini API Key", type="password", help="Google AI Studio에서 발급받은 키를 입력하세요.")
    
    st.divider()
    
    selected_date = st.date_input("여행 기준 날짜", datetime.today())
    currency = st.selectbox("현지 통화", ["USD", "JPY", "EUR", "CNY", "GBP", "VND"])
    
    with st.spinner(f'{selected_date} 기준 환율 조회 중...'):
        # [핵심] 선택한 날짜(selected_date)를 함수에 전달!
        current_rate = get_exchange_rate(currency, selected_date)
    
    if current_rate:
        display_rate = current_rate * 100 if currency in ["JPY", "VND"] else current_rate
        unit = 100 if currency in ["JPY", "VND"] else 1
        st.metric(label=f"환율 ({unit} {currency})", value=f"{display_rate:.2f} KRW")
    else:
        current_rate = 1000.0
        st.warning("환율 조회 실패. 기본값(1000) 사용")

# ==========================================
# 3. 메인: 영수증 입력 및 AI 분석
# ==========================================
st.subheader("🧾 지출 기록하기")

col1, col2 = st.columns([1, 2])

with col1:
    uploaded_file = st.file_uploader("영수증 업로드", type=['jpg', 'png', 'jpeg'])
    if uploaded_file:
        # PIL 이미지로 변환
        image = Image.open(uploaded_file)
        st.image(image, caption='이미지 미리보기', use_column_width=True)

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
                
                st.success("분석 완료! 아래 내용을 확인하고 등록하세요.")

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
            cat_index = 5 # 기타
            
        input_category = st.selectbox("카테고리", options, index=cat_index)
        input_price = st.number_input(f"금액 ({currency})", min_value=0.0, format="%.2f", value=st.session_state.form_price)
        
        submitted = st.form_submit_button("💾 지출 등록하기")
        
        if submitted:
            price_krw = input_price * current_rate
            record = {
                "날짜": input_date.strftime("%Y-%m-%d"),
                "가게명": input_store,
                "카테고리": input_category,
                "현지금액": input_price,
                "통화": currency,
                "환산금액(KRW)": int(price_krw),
                "적용환율": current_rate
            }
            st.session_state.expenses.append(record)
            st.success("리스트에 추가되었습니다!")

# ==========================================
# 4. 데이터 시각화
# ==========================================
if st.session_state.expenses:
    st.divider()
    df = pd.DataFrame(st.session_state.expenses)
    
    st.subheader("📊 통계 및 내역")
    
    # 1행 2열 차트 배치
    c1, c2 = st.columns(2)
    with c1:
        fig_bar = px.bar(df, x="날짜", y="환산금액(KRW)", color="카테고리", title="일자별/카테고리별 지출")
        st.plotly_chart(fig_bar, use_container_width=True)
    with c2:
        fig_pie = px.pie(df, values="환산금액(KRW)", names="카테고리", title="카테고리별 비중")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.dataframe(df, use_container_width=True)
    
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("엑셀 다운로드", csv, "travel_log.csv", "text/csv")