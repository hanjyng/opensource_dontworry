import streamlit as st
import plotly.express as px
from datetime import datetime
from PIL import Image
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim # [추가] 주소 -> 좌표 변환용
import re  # [필수] 맨 위 import 구문에 추가하거나, 함수 안에서 import 해도 됨

# 모듈 임포트
import modules.sqlite3_db as db
from modules.llm_gemini import analyze_receipt
from modules.exchange import get_exchange_rate
from modules.to_excel import to_excel
from modules.to_pdf import create_pdf


# 1. 페이지 설정
st.set_page_config(page_title="AI 여행 가계부", layout="wide")
st.title("Don't ₩orry | ✈️ AI 스마트 여행 가계부")

# 앱 시작 시 DB 초기화 실행 (파일이 없으면 생성됨)
db.init_db()

# ==========================================
# 세션 상태 관리 (AI 폼 채우기용만 남김)
# ==========================================
if 'form_date' not in st.session_state: st.session_state.form_date = datetime.today()
if 'form_store' not in st.session_state: st.session_state.form_store = ""
if 'form_address' not in st.session_state: st.session_state.form_address = "" # [추가] 주소
if 'form_category' not in st.session_state: st.session_state.form_category = "식비"
if 'form_price' not in st.session_state: st.session_state.form_price = 0.0
if 'form_linked_mem' not in st.session_state: st.session_state.form_linked_mem = None # [추가] 연결된 추억 ID

# 편집 상태 관리
if 'expense_edit_id' not in st.session_state: st.session_state.expense_edit_id = None
if 'memory_edit_id' not in st.session_state: st.session_state.memory_edit_id = None

# 삭제 확인용 상태
if 'delete_confirm_type' not in st.session_state: st.session_state.delete_confirm_type = None # 'expense' or 'memory'
if 'delete_target_id' not in st.session_state: st.session_state.delete_target_id = None

# 추억 - 구글맵 줌 위치
if 'map_center' not in st.session_state: st.session_state.map_center = [37.5665, 126.9780]
if 'map_zoom' not in st.session_state: st.session_state.map_zoom = 14

# 지출 선택 변경 감지용 변수 초기화
if 'last_sel_exp_id' not in st.session_state: st.session_state.last_sel_exp_id = None

# ==========================================
# 2. 사이드바 설정 (공통)
# ==========================================
with st.sidebar:
    st.header("⚙️ 설정")
    api_key = st.text_input("Google Gemini API Key", type="password", 
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
    
    # [중요] 수정 모드 탈출 버튼 (활성화)
    st.divider()
    if st.button("🔄 모든 입력/수정 폼 초기화"):
        st.session_state.expense_edit_id = None
        st.session_state.memory_edit_id = None
        st.session_state.form_store = ""
        st.session_state.form_address = ""
        st.session_state.form_price = 0.0
        st.session_state.form_linked_mem = None
        st.rerun()

# ==========================================
# 헬퍼 함수: 삭제 확인 다이얼로그
# ==========================================
@st.dialog("삭제 확인")
def confirm_delete_dialog(item_type, item_id, is_linked):
    if is_linked:
        st.warning(f"⚠️ 이 항목은 다른 {('추억' if item_type == 'expense' else '지출')} 데이터와 연결되어 있습니다.")
        st.write("삭제하시면 연결된 정보에서도 참조가 해제됩니다.")
    else:
        st.write("정말 삭제하시겠습니까?")
        
    if st.button("네, 삭제합니다", type="primary"):
        if item_type == 'expense':
            db.delete_expense(item_id)
        else:
            db.delete_memory(item_id)
        
        st.success("삭제되었습니다.")
        st.session_state.delete_confirm_type = None
        st.session_state.expense_edit_id = None
        st.session_state.memory_edit_id = None
        st.rerun()

# ==========================================
# 헬퍼 함수: 주소 -> 좌표 변환
# ==========================================
def get_lat_lon_from_address(address):
    """주소를 위경도로 변환 (실패 시 None 반환)"""
    try:
        # 타임아웃을 10초로 늘려 안정성 확보
        geolocator = Nominatim(user_agent="dont_worry_travel_app_v1", timeout=10)
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        else:
                # [디버깅] 변환 실패한 주소를 터미널에 출력
                print(f"[Geocoding Fail] '{address}' -> 찾을 수 없음") 
                return None
    except Exception as e:
        print(f"[Geocoding Error] {e}")
        return None
def get_lat_lon_from_address2(address):
    """
    주소를 위경도로 변환 (실패 시 상세 주소 제거 후 재시도)
    """
    try:
        geolocator = Nominatim(user_agent="dont_worry_travel_app_v1", timeout=10)
        
        # ---------------------------------------------------------
        # 1차 시도: 원본 주소 그대로 검색
        # ---------------------------------------------------------
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
            
        # ---------------------------------------------------------
        # 2차 시도: 상세 주소(Suite, Unit, # 등) 제거 후 검색
        # 예: "334 Santana Row Suite 1065..." -> "334 Santana Row..."
        # ---------------------------------------------------------
        print(f"[1차 실패] 상세 주소 제거 후 재시도: {address}")
        
        # 정규표현식으로 Suite/Unit/호수 등 제거
        # (?i): 대소문자 무시
        # (suite|unit|...): 제거할 키워드들
        # \s*: 공백
        # [\w-]+: 뒤따라오는 숫자나 문자 (예: 1065, A-1 등)
        clean_address = re.sub(r'(?i)(suite|unit|apt|room|floor|#)\s*[\w-]+', '', address)
        
        # 쉼표(,)가 여러 개 겹치면 하나로 정리
        clean_address = re.sub(r',\s*,', ',', clean_address).strip()
        
        if clean_address != address: # 주소가 조금이라도 바뀌었다면 재시도
            print(f"[2차 시도] {clean_address}")
            location = geolocator.geocode(clean_address)
            if location:
                return location.latitude, location.longitude

    except Exception as e:
        print(f"[Geocoding Error] {e}")
        return None
        
    return None

# ==========================================
# 메인 탭 구성: 지출 관리 / 추억 지도
# ==========================================
tab1, tab2 = st.tabs(["💰 지출 관리", "🗺️ 추억 지도"])

# 데이터 미리 로드 (Selectbox 구성을 위해 필요)
memories_df = db.load_memories()
expenses_df = db.load_expenses()

# -----------------------------------------------------------------------------
# TAB 1: 지출 관리 기능
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("🧾 지출 기록하기")
    col1, col2 = st.columns([1, 2])

    with col1: # --- 왼쪽: 영수증 업로드 ---
        uploaded_file = st.file_uploader("영수증 업로드", type=['jpg', 'png', 'jpeg'])
        if uploaded_file:
            image = Image.open(uploaded_file) # PIL 이미지로 변환
            st.image(image, caption='이미지 미리보기', use_container_width=True)
    
    with col2: # --- 오른쪽: 입력/수정 폼 ---
        if st.session_state.expense_edit_id:
            st.info(f"✏️ [지출 수정 모드] ID: {st.session_state.expense_edit_id}")
        else:
            # 신규 입력 모드일 때만 AI 분석 버튼 표시
            
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
                        st.session_state.form_address = analyzed_data.get('address', '') # [추가]
                        st.session_state.form_category = analyzed_data.get('category', '기타')
                        st.session_state.form_price = float(analyzed_data.get('price', 0.0))
                        
                        st.success("분석 완료! 아래 내용을 확인 후 등록하세요.")

        # -------------------------------------------------------
        # 입력 폼 (AI 분석 결과가 value로 들어감)
        # -------------------------------------------------------
        with st.form("expense_form"):
            # value 파라미터에 st.session_state 값을 연결하여 자동 채움 구현
            input_date = st.date_input("날짜", value=st.session_state.form_date)
            input_store = st.text_input("가게명", value=st.session_state.form_store)
            input_address = st.text_input("주소 (위치 정보)", value=st.session_state.form_address) 
            
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
                value=st.session_state.form_price
            )
            
            # [추가] 추억 연결 선택 (1:1 매칭을 위해)
            # option list: "ID: 제목" 형태
            mem_opts = {f"{r['id']}: {r['location_name']} ({r['date']})": r['id'] for _, r in memories_df.iterrows()}
            mem_opts["(연결 안 함)"] = None # 기본값
            
            # 현재 선택된 값이 있는지 확인
            current_mem_val = st.session_state.form_linked_mem
            # 리스트에서의 인덱스 찾기
            mem_keys = list(mem_opts.keys())
            try:
                # 역으로 ID를 통해 키를 찾음
                found_key = next(k for k, v in mem_opts.items() if v == current_mem_val)
                mem_idx = mem_keys.index(found_key)
            except:
                mem_idx = len(mem_keys) - 1 # (연결 안 함)

            selected_mem_key = st.selectbox("🔗 이 지출과 연결할 추억 선택", mem_keys, index=mem_idx)
            selected_mem_id = mem_opts[selected_mem_key]
            
            # 제출 버튼 라벨 동적 변경
            if st.session_state.expense_edit_id:
                submit_label = "✏️ 수정사항 저장"
            else:
                submit_label = "💾 지출 등록하기"
            
            submitted = st.form_submit_button(submit_label)
            
            if submitted:
                price_krw = input_price * current_rate
                
                if st.session_state.expense_edit_id:
                    db.update_expense(
                        st.session_state.expense_edit_id,
                        input_date.strftime("%Y-%m-%d"), input_store, input_address, input_category,
                        input_price, currency, price_krw, current_rate, selected_mem_id
                    )
                    st.success("수정되었습니다.")
                    st.session_state.expense_edit_id = None
                else:
                    db.save_expense(
                        input_date.strftime("%Y-%m-%d"), input_store, input_address, input_category,
                        input_price, currency, price_krw, current_rate, selected_mem_id
                    )
                    st.success("등록되었습니다.")
                
                # 폼 초기화 (선택 사항)
                st.session_state.expense_edit_id = None
                st.session_state.form_store = ""
                st.session_state.form_price = 0.0
                st.session_state.form_linked_mem = None
                st.rerun() # 화면 갱신
            
        # [삭제 버튼] 수정 모드일 때만 폼 바깥에 표시
        if st.session_state.expense_edit_id:
            if st.button("🗑️ 이 내역 삭제하기", key="del_exp_btn", type="primary"):
                # 연결 여부 확인
                row = expenses_df[expenses_df['id'] == st.session_state.expense_edit_id].iloc[0]
                # NOTE: sqlite3 ID 기본적으로 1부터 시작 
                # `INTEGER PRIMARY KEY AUTOINCREMENT` or `INTEGER PRIMARY KEY` 사용할 때  
                is_linked = True if (row['linked_memory_id'] and row['linked_memory_id'] > 0) else False
                confirm_delete_dialog("expense", st.session_state.expense_edit_id, is_linked)
                

    # ==========================================
    # 4. 데이터 시각화 (DB 연동)
    # ==========================================
    st.divider()
    st.subheader("📊 지출 내역")
    st.caption("💡 표의 행을 클릭하면 상단 폼에서 수정하거나 삭제할 수 있습니다.")

    # DB에서 데이터 불러오기
    # df = db.load_expenses()

    if not expenses_df.empty:
        # 표시용 DF 생성
        display_df = expenses_df.rename(columns={
            # 'id': 'ID', # 화면에 ID를 보여주고 싶으면 주석 해제
            'date': '날짜',
            'store_name': '가게명',
            'address': '주소',
            'category': '카테고리',
            'price_foreign': '현지 금액',
            'currency': '통화',
            'price_krw': '환산금액(KRW)',
            'exchange_rate': '적용환율',
            'linked_memory_id': '연결된추억ID'
        })
        
        # event = st.dataframe(
        #     display_df,
        #     use_container_width=True,
        #     hide_index=True,
        #     on_select="rerun",  # 선택 시 앱 리런
        #     selection_mode="single-row" # 한 줄만 선택/수정 가능
        # )
        event = st.dataframe(
            # display_df[['ID', '날짜', '가게명', '주소', '카테고리', '현지 금액', '환산금액(KRW)', '적용환율', '연결된추억ID']],
            display_df,
            use_container_width=True, hide_index=True, on_select="rerun", 
            selection_mode="single-row" # 한 줄만 선택/수정 가능
        )
        # 사용자가 행을 클릭했는지 확인
        if event.selection.rows:
            sel_idx = event.selection.rows[0]
            real_id = int(expenses_df.iloc[sel_idx]['id'])
            
            if st.session_state.expense_edit_id != real_id:
                row = expenses_df.iloc[sel_idx]
                st.session_state.expense_edit_id = real_id
                st.session_state.form_date = datetime.strptime(row['date'], "%Y-%m-%d")
                st.session_state.form_store = row['store_name']
                st.session_state.form_address = row['address'] if row['address'] else ""
                st.session_state.form_category = row['category']
                st.session_state.form_price = float(row['price_foreign'])
                # float NaN 처리를 위해 int 변환 시도
                try: st.session_state.form_linked_mem = int(row['linked_memory_id'])
                except: st.session_state.form_linked_mem = None
                st.rerun()
        
        # --- 통계 그래프 ---
        c1, c2 = st.columns(2)
        with c1:
            # groupby 자동 처리를 위해 plotly가 편리함
            fig_bar = px.bar(
                display_df, 
                x="날짜", y="환산금액(KRW)", 
                color="카테고리", 
                title="일자별/카테고리별 지출")
            st.plotly_chart(fig_bar, use_container_width=True)
        with c2:
            fig_pie = px.pie(display_df, values="환산금액(KRW)", names="카테고리", title="카테고리별 비중")
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # -------------------------------------------------------
        # 내보내기 - 다운로드 버튼 영역 (CSV / Excel / PDF)
        # -------------------------------------------------------
        st.subheader("📥 데이터 내보내기")
        
        # 약 1 : 1 : 1 비율로 버튼 자리를 만들고, 나머지(7)는 빈 공간으로 둠
        d_col1, d_col2, d_col3, empty_space = st.columns([1, 1.075, 1, 6.925])
        
        # 1. CSV 다운로드 기능 (DB 데이터를 기반으로 생성)
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        d_col1.download_button(
            label="📄 CSV 다운로드",
            data=csv,
            file_name="Don't ₩orry.csv",
            mime="text/csv",
            use_container_width=True # 버튼을 컬럼 너비에 꽉 차게)
        )
        
        # 2. Excel 다운로드
        excel_data = to_excel(display_df)
        d_col2.download_button(
            label="📊 Excel 다운로드",
            data=excel_data,
            file_name="Don't ₩orry.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True
        )

        # 3. PDF 다운로드
        try:
            # 주의: 한글 폰트가 없으면 PDF 생성 시 에러가 나거나 글자가 깨질 수 있음
            
            pdf_data = create_pdf(display_df)
            d_col3.download_button(
                label="📕 PDF 다운로드",
                data=pdf_data,
                file_name="Don't ₩orry.pdf",
                mime='application/pdf',
                use_container_width=True
            )
        except Exception as e:
            d_col3.error(f"PDF 생성 실패: {e}")

    else:
        st.info("아직 저장된 지출 내역이 없습니다.")


# -----------------------------------------------------------------------------
# TAB 2: 추억 지도 (Google Map 스타일) 기능 추가
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("📍 나만의 여행 지도")
    
    # ---------------------------------
    # 상단: 지도 및 입력 폼
    # ---------------------------------
    m_col1, m_col2 = st.columns([2, 1])

    # --- 지도 표시 영역 (왼쪽) ---
    with m_col1:
        # 지도의 중심 좌표 설정 (데이터가 있으면 마지막 데이터 기준, 없으면 서울)
        # 편집 중인 추억이 있다면 그 위치를 중심으로, 없다면 기존 로직
        # if st.session_state.memory_edit_id:
        #     target_row = memories_df[memories_df['id'] == st.session_state.memory_edit_id]
        #     if not target_row.empty:
        #         st.session_state.map_center = [target_row.iloc[0]['lat'], target_row.iloc[0]['lon']]
        #         st.session_state.map_zoom = 16 # 좀 더 확대
        # elif not memories_df.empty and st.session_state.map_center == [37.5665, 126.9780]:
        #     # 데이터는 있는데 중심이 서울(기본값)이라면 첫 데이터로 이동
        #     st.session_state.map_center = [memories_df.iloc[0]['lat'], memories_df.iloc[0]['lon']]
        # if not memories_df.empty:
        #     center_lat = memories_df.iloc[0]['lat']
        #     center_lon = memories_df.iloc[0]['lon']
        # else:
        #     center_lat, center_lon = 37.5665, 126.9780  # 서울 시청

        # Folium 지도 생성
        m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)
        
        # 저장된 마커(핀) 찍기
        for idx, row in memories_df.iterrows():
            # 팝업에 들어갈 HTML 생성 (사진 포함)
            popup_html = f"""
            <div style="width:200px">
                <b>{row['location_name']}</b><br>
                <small>{row['date']}</small><br>
                <p>{row['comment']}</p>
            """
            if row['image_data']: # 이미지가 있다면 표시
                popup_html += f'<img src="data:image/jpeg;base64,{row["image_data"]}" width="100%"><br>'
            if row['linked_expense_id'] and row['linked_expense_id']>0: # 참조하는 지출이 있다면 지출 ID 표시
                popup_html += f"(Linked Exp: {int(row['linked_expense_id'])})"
            popup_html += "</div>"
            
            # 마커 생성
            marker = folium.Marker(
                [row['lat'], row['lon']],
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=row['location_name'],
                icon=folium.Icon(color='red', icon='heart')
            )
            marker.add_to(m)
        
        # 지도 출력 및 클릭 이벤트 받기
        st.caption("👇 지도에서 핀을 클릭하면 내용이 표시되고, 빈 곳을 클릭하면 위치가 입력됩니다.")
        # map_data = st_folium(m, height=500, use_container_width=True)
        # [핵심] st_folium에서 반환된 데이터 (클릭 이벤트 포함)
        # return_on_hover=False로 설정해야 클릭 시에만 리턴됨
        map_data = st_folium(m, height=500, use_container_width=True, return_on_hover=False)

    # --- 추억 입력 영역 (오른쪽) ---
    with m_col2:
        st.write("#### 📝 추억 기록/수정")
        
        # 지도 인터랙션 처리 로직 
        if map_data:
            # 핀(Marker) 클릭 감지
            if map_data and map_data['last_object_clicked']:
                clicked_lat = map_data['last_object_clicked']['lat']
                clicked_lng = map_data['last_object_clicked']['lng']
                
                # 좌표로 데이터 찾기
                matched_row = memories_df[
                    (memories_df['lat'].round(6) == round(clicked_lat, 6)) & 
                    (memories_df['lon'].round(6) == round(clicked_lng, 6))
                ]
                
                if not matched_row.empty:
                    found_id = int(matched_row.iloc[0]['id'])
                    # 현재 편집 ID와 다를 때만 업데이트 후 리런 (폼 채우기 위해)
                    if st.session_state.memory_edit_id != found_id:
                        st.session_state.memory_edit_id = found_id
                        st.rerun()
            
        # 편집 모드일 때 데이터 로드 (폼 채우기)
        if st.session_state.memory_edit_id is not None:
            st.info(f"✏️ [추억 수정] ID: {st.session_state.memory_edit_id}")
            # 현재 편집중인 데이터 찾기
            edit_mem_row = memories_df[memories_df['id'] == st.session_state.memory_edit_id]
            if not edit_mem_row.empty:
                edit_mem_row = edit_mem_row.iloc[0]
                def_date = datetime.strptime(edit_mem_row['date'], "%Y-%m-%d")
                def_loc = edit_mem_row['location_name']
                def_com = edit_mem_row['comment']
                def_lat = float(edit_mem_row['lat'])
                def_lon = float(edit_mem_row['lon'])
                try: def_link = int(edit_mem_row['linked_expense_id'])
                except: def_link = None
            else:
                # ID는 있는데 데이터가 없는 경우 (삭제 직후 등) 초기화
                st.session_state.memory_edit_id = None
                st.rerun()
            
        else:
            # 신규 모드 (지도 클릭 좌표 반영)
            def_date = datetime.today()
            def_loc = ""
            def_com = ""
            def_link = None
            
            if map_data and map_data['last_clicked']:
                def_lat = map_data['last_clicked']['lat']
                def_lon = map_data['last_clicked']['lng']
            else:
                def_lat = st.session_state.map_center[0]
                def_lon = st.session_state.map_center[1]
        
        
        # =========================================================
        # 참조 지출 선택시 위치 확인 후 구글맵 이동 ~
        # 지출 연결 선택을 Form 바깥으로 이동 (즉시 반응 위해)
        st.caption("먼저 연결할 지출을 선택하면 해당 위치로 지도가 이동합니다.")
        
        # 1. 옵션 리스트 생성
        exp_opts = {f"{r['id']}: {r['store_name']} ({int(r['price_krw'])}원)": r['id'] for _, r in expenses_df.iterrows()}
        exp_opts["(연결 안 함)"] = None
        exp_keys = list(exp_opts.keys())
        
        # 2. 기본 인덱스 찾기
        try:
            found_exp_key = next(k for k, v in exp_opts.items() if v == def_link)
            exp_idx = exp_keys.index(found_exp_key)
        except:
            exp_idx = len(exp_keys) - 1 # (연결 안 함)

        # 3. Selectbox (Form 바깥)
        sel_exp_key = st.selectbox("🔗 위치를 확인할 지출 선택", exp_keys, index=exp_idx, key="mem_link_select")
        sel_exp_id = exp_opts[sel_exp_key]

        # 4. [기능 추가] 선택 변경 시 지도 이동 로직
        # 이전 선택값과 현재 선택값이 다르고, 선택된 지출이 있다면
        # if 'last_sel_exp_id' not in st.session_state: st.session_state.last_sel_exp_id = None

        # 4. [수정됨] 선택 변경 시 지도 이동 로직
        # 사용자가 "연결 안 함"이 아닌 유효한 지출을 '새로' 선택했을 때
        if sel_exp_id is not None and sel_exp_id != st.session_state.last_sel_exp_id:
            
            # 해당 지출 정보 가져오기
            target_exp = expenses_df[expenses_df['id'] == sel_exp_id]
            
            if not target_exp.empty:
                raw_addr = target_exp.iloc[0]['address']
                # 주소 값이 비어있지 않은지 확인
                if raw_addr and isinstance(raw_addr, str) and raw_addr.strip():
                    st.toast(f"🌏 좌표 변환 시도 중: {raw_addr}") # 진행상황 표시
                    
                    coords = get_lat_lon_from_address2(raw_addr)
                    
                    if coords:
                        # 성공 시 지도 중심 이동
                        st.session_state.map_center = [coords[0], coords[1]]
                        st.session_state.map_zoom = 16
                        st.session_state.last_sel_exp_id = sel_exp_id # 업데이트 성공 시에만 상태 변경
                        st.success(f"📍 '{raw_addr}' 위치로 이동했습니다!")
                        st.rerun() # 즉시 리런하여 지도 다시 그림
                    else:
                        st.error(f"⚠️ 주소 변환 실패: '{raw_addr}'\n\n정확한 도로명 주소인지 확인해주세요.")
                else:
                    st.warning("⚠️ 선택한 지출 내역에 저장된 '주소' 정보가 없습니다.")
            
            # 변환에 실패했더라도, 무한 반복을 막기 위해 last_id는 업데이트 하는 게 나을 수도 있음
            # 하지만 위에서는 성공할 때만 리런하도록 처리함.
            st.session_state.last_sel_exp_id = sel_exp_id 

        # "연결 안 함" 선택 시 상태 초기화
        if sel_exp_id is None:
            st.session_state.last_sel_exp_id = None
        # ~ 참조 지출 선택시 위치 확인 후 구글맵 이동
        # =========================================================
        
        # -----------------------------------
        # 입력/수정 폼 
        # -----------------------------------
        with st.form("memory_form"):
            mem_date = st.date_input("날짜", value=def_date)
            mem_loc = st.text_input("장소명", value=def_loc)
            mem_comment = st.text_area("메모", value=def_com)
            
            c1, c2 = st.columns(2)
            in_lat = c1.number_input("위도", value=def_lat, format="%.6f")
            in_lon = c2.number_input("경도", value=def_lon, format="%.6f")
            
            mem_photo = st.file_uploader("사진", type=['jpg','png','jpeg'])
            
            # 지출 연결 선택
            exp_opts = {f"{r['id']}: {r['store_name']} ({int(r['price_krw'])}원)": r['id'] for _, r in expenses_df.iterrows()}
            exp_opts["(연결 안 함)"] = None
            # 현재 선택된 인덱스 찾기
            exp_keys = list(exp_opts.keys())
            try:
                found_exp_key = next(k for k, v in exp_opts.items() if v == def_link)
                exp_idx = exp_keys.index(found_exp_key)
            except:
                exp_idx = len(exp_keys) - 1
            
            sel_exp_key = st.selectbox("🔗 이 추억과 연결할 지출 선택", exp_keys, index=exp_idx)
            sel_exp_id = exp_opts[sel_exp_key]
            
            
            # 저장 버튼
            btn_txt = "💾 수정 저장" if st.session_state.memory_edit_id else "📍 핀 저장"
            if st.form_submit_button(btn_txt):
                if mem_loc:
                    if st.session_state.memory_edit_id:
                        db.update_memory(
                            st.session_state.memory_edit_id,
                            mem_date.strftime("%Y-%m-%d"), mem_loc, mem_comment, 
                            in_lat, in_lon, mem_photo, sel_exp_id
                        )
                        st.success("수정 완료")
                        st.session_state.memory_edit_id = None # 수정 후 신규 모드로
                    else:
                        db.save_memory(
                            mem_date.strftime("%Y-%m-%d"), mem_loc, mem_comment, 
                            in_lat, in_lon, mem_photo, sel_exp_id
                        )
                        st.success("저장 완료")
                    st.rerun()
                else:
                    st.error("장소명을 입력하세요.")
        
        # 삭제 버튼 (수정 모드일 때)
        if st.session_state.memory_edit_id:
            if st.button("🗑️ 삭제하기", key="del_mem_btn", type="primary"):
                row = memories_df[memories_df['id'] == st.session_state.memory_edit_id].iloc[0]
                is_linked = True if (row['linked_expense_id'] and row['linked_expense_id'] > 0) else False
                confirm_delete_dialog("memory", st.session_state.memory_edit_id, is_linked)
        
    # ---------------------------------
    # 하단: 추억 리스트 (테이블)
    # ---------------------------------
    st.divider()
    st.subheader("📒 추억 목록 관리")
    
    if not memories_df.empty:
        # 표시용 DF
        disp_mem = memories_df.rename(columns={
            'id': 'ID', 'date': '날짜', 'location_name': '장소', 'comment': '메모',
            'linked_expense_id': '연결된지출ID'
        })
        
        # 추억 데이터 테이블 표시 & 선택 
        mem_event = st.dataframe(
            disp_mem[['ID', '날짜', '장소', '메모', '연결된지출ID']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        # 리스트 선택 시에만 '지도 중심 이동' 수행
        if mem_event.selection.rows:
            sel_idx = mem_event.selection.rows[0]
            real_mem_id = int(memories_df.iloc[sel_idx]['id'])
            
            # 목록 클릭 시 -> 편집 모드로 전환 + 지도 중심 이동
            if st.session_state.memory_edit_id != real_mem_id:
                st.session_state.memory_edit_id = real_mem_id
                
                # 선택된 추억의 좌표로 지도 중심 이동 설정
                sel_row = memories_df.iloc[sel_idx]
                st.session_state.map_center = [sel_row['lat'], sel_row['lon']]
                st.session_state.map_zoom = 16 # 줌 레벨 확대
                
                st.rerun()
    else:
        st.info("저장된 추억이 없습니다.")