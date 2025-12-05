import streamlit as st
import plotly.express as px
from datetime import datetime
from PIL import Image
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim 
import re  # [추가] 정규표현식 모듈 (주소 정제용)

# 커스텀 모듈 임포트 (파일이 존재한다고 가정)
import modules.sqlite3_db as db
from modules.llm_gemini import analyze_receipt
from modules.exchange import get_exchange_rate
from modules.to_excel import to_excel
from modules.to_pdf import create_pdf


# 1. 페이지 설정
st.set_page_config(page_title="AI 여행 가계부", layout="wide")
st.title("Don't ₩orry | ✈️ AI 스마트 여행 가계부")

# 앱 시작 시 DB 초기화 실행
db.init_db()

# ==========================================
# 세션 상태 관리 (초기화)
# ==========================================
if 'form_date' not in st.session_state: st.session_state.form_date = datetime.today()
if 'form_store' not in st.session_state: st.session_state.form_store = ""
if 'form_address' not in st.session_state: st.session_state.form_address = ""
if 'form_search_address' not in st.session_state: st.session_state.form_search_address = ""
if 'form_gemini_lat' not in st.session_state: st.session_state.form_gemini_lat = None
if 'form_gemini_lon' not in st.session_state: st.session_state.form_gemini_lon = None
if 'form_category' not in st.session_state: st.session_state.form_category = "식비"
if 'form_price' not in st.session_state: st.session_state.form_price = 0.0
if 'form_linked_mem' not in st.session_state: st.session_state.form_linked_mem = None

# 편집 상태 관리
if 'expense_edit_id' not in st.session_state: st.session_state.expense_edit_id = None
if 'memory_edit_id' not in st.session_state: st.session_state.memory_edit_id = None
if 'delete_confirm_type' not in st.session_state: st.session_state.delete_confirm_type = None
if 'delete_target_id' not in st.session_state: st.session_state.delete_target_id = None

# 지도 관련 상태
if 'map_center' not in st.session_state: st.session_state.map_center = [37.5665, 126.9780]
if 'map_zoom' not in st.session_state: st.session_state.map_zoom = 14
if 'last_sel_exp_id' not in st.session_state: st.session_state.last_sel_exp_id = None


# ==========================================
# 2. 사이드바 설정
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
    
    st.divider()
    if st.button("🔄 모든 입력/수정 폼 초기화"):
        st.session_state.expense_edit_id = None
        st.session_state.memory_edit_id = None
        st.session_state.form_store = ""
        st.session_state.form_address = ""
        st.session_state.form_search_address = ""
        st.session_state.form_gemini_lat = None
        st.session_state.form_gemini_lon = None
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
# 헬퍼 함수: 주소 -> 좌표 변환 (통합 및 개선)
# ==========================================
def get_lat_lon_from_address(address):
    """
    주소를 위경도로 변환 (1차: 원본, 2차: 상세주소 제거 후 재시도)
    Photon(Elasticsearch 기반) 사용
    """
    if not address: return None

    try:
        geolocator = Nominatim(user_agent="dont_worry_travel_app_v1", timeout=10)
        
        # 1차 시도: 원본 주소
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
            
        # 2차 시도: 상세 주소(Suite, Unit, # 등) 제거 후 검색
        # 예: "334 Santana Row Suite 1065..." -> "334 Santana Row..."
        print(f"[1차 실패] 상세 주소 제거 후 재시도: {address}")
        
        clean_address = re.sub(r'(?i)(suite|unit|apt|room|floor|#)\s*[\w-]+', '', address)
        clean_address = re.sub(r',\s*,', ',', clean_address).strip() # 쉼표 정리
        
        if clean_address != address: 
            print(f"[2차 시도] {clean_address}")
            location = geolocator.geocode(clean_address)
            if location:
                return location.latitude, location.longitude

    except Exception as e:
        print(f"[Geocoding Error] {e}")
        return None
        
    return None

# ==========================================
# 메인 탭 구성
# ==========================================
tab1, tab2 = st.tabs(["💰 지출 관리", "🗺️ 추억 지도"])

# DB 데이터 로드
memories_df = db.load_memories()
expenses_df = db.load_expenses()

# -----------------------------------------------------------------------------
# TAB 1: 지출 관리 기능
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("🧾 지출 기록하기")
    col1, col2 = st.columns([1, 2])

    with col1: # --- 영수증 업로드 ---
        uploaded_file = st.file_uploader("영수증 업로드", type=['jpg', 'png', 'jpeg'])
        if uploaded_file:
            image = Image.open(uploaded_file)
            st.image(image, caption='이미지 미리보기', use_container_width=True)
    
    with col2: # --- 입력/수정 폼 ---
        if st.session_state.expense_edit_id:
            st.info(f"✏️ [지출 수정 모드] ID: {st.session_state.expense_edit_id}")
        else:
            # 신규 입력 모드: AI 분석 버튼
            if not api_key:
                st.warning("👈 사이드바에 Gemini API Key를 먼저 입력해주세요.")
            
            if uploaded_file and api_key and st.button("🤖 AI 영수증 분석 실행"):
                with st.spinner('Gemini가 영수증을 읽고 있습니다...'):
                    analyzed_data = analyze_receipt(image, api_key)
                    if analyzed_data:
                        try:
                            st.session_state.form_date = datetime.strptime(analyzed_data.get('date', str(selected_date)), "%Y-%m-%d")
                        except:
                            st.session_state.form_date = selected_date
                        
                        st.session_state.form_store = analyzed_data.get('store_name', '')
                        st.session_state.form_address = analyzed_data.get('address', '')
                        
                        search_addr = analyzed_data.get('search_address', '')
                        st.session_state.form_search_address = search_addr if search_addr else analyzed_data.get('address', '')
                        
                        # Gemini 추정 좌표 저장
                        st.session_state.form_gemini_lat = analyzed_data.get('estimated_lat')
                        st.session_state.form_gemini_lon = analyzed_data.get('estimated_lon')
                        
                        st.session_state.form_category = analyzed_data.get('category', '기타')
                        st.session_state.form_price = float(analyzed_data.get('price', 0.0))
                        
                        st.success("분석 완료! 아래 내용을 확인 후 등록하세요.")

        with st.form("expense_form"):
            input_date = st.date_input("날짜", value=st.session_state.form_date)
            input_store = st.text_input("가게명", value=st.session_state.form_store)
            
            input_address = st.text_input("주소", value=st.session_state.form_address)
            # c_addr1, c_addr2 = st.columns(2)
            # with c_addr1:
            #     input_address = st.text_input("주소 (표시용)", value=st.session_state.form_address)
            # with c_addr2:
            input_search_address = st.text_input("주소 (지도 검색용)", value=st.session_state.form_search_address)

            # (옵션) AI 추정 좌표가 있다는 것을 표시 (수정 불가)
            if st.session_state.form_gemini_lat and st.session_state.form_gemini_lon:
                st.caption(f"🤖 AI 추정 좌표 확보: {st.session_state.form_gemini_lat}, {st.session_state.form_gemini_lon}")

            options = ["식비", "쇼핑", "관광", "교통", "숙박", "기타"]
            try: cat_index = options.index(st.session_state.form_category)
            except: cat_index = 5
            
            input_category = st.selectbox("카테고리", options, index=cat_index)
            input_price = st.number_input(f"금액 ({currency})", min_value=0.0, format="%.2f", value=st.session_state.form_price)
            
            mem_opts = {f"{r['id']}: {r['location_name']} ({r['date']})": r['id'] for _, r in memories_df.iterrows()}
            mem_opts["(연결 안 함)"] = None
            current_mem_val = st.session_state.form_linked_mem
            mem_keys = list(mem_opts.keys())
            try:
                found_key = next(k for k, v in mem_opts.items() if v == current_mem_val)
                mem_idx = mem_keys.index(found_key)
            except: mem_idx = len(mem_keys) - 1

            selected_mem_key = st.selectbox("🔗 이 지출과 연결할 추억 선택", mem_keys, index=mem_idx)
            selected_mem_id = mem_opts[selected_mem_key]
            
            submit_label = "✏️ 수정사항 저장" if st.session_state.expense_edit_id else "💾 지출 등록하기"
            submitted = st.form_submit_button(submit_label)
            
            if submitted:
                price_krw = input_price * current_rate
                # 현재 세션 상태의 Gemini 좌표 사용 (수정 시에는 유지 또는 업데이트)
                g_lat = st.session_state.form_gemini_lat
                g_lon = st.session_state.form_gemini_lon

                if st.session_state.expense_edit_id:
                    db.update_expense(
                        st.session_state.expense_edit_id,
                        input_date.strftime("%Y-%m-%d"), input_store, input_address, input_search_address,
                        g_lat, g_lon, # [추가]
                        input_category, input_price, currency, price_krw, current_rate, selected_mem_id
                    )
                    st.success("수정되었습니다.")
                    st.session_state.expense_edit_id = None
                else:
                    db.save_expense(
                        input_date.strftime("%Y-%m-%d"), input_store, input_address, input_search_address,
                        g_lat, g_lon, # [추가]
                        input_category, input_price, currency, price_krw, current_rate, selected_mem_id
                    )
                    st.success("등록되었습니다.")
                
                st.session_state.form_store = ""
                st.session_state.form_price = 0.0
                st.session_state.form_address = ""
                st.session_state.form_search_address = ""
                st.session_state.form_gemini_lat = None
                st.session_state.form_gemini_lon = None
                st.session_state.form_linked_mem = None
                st.rerun()
            
        # 삭제 버튼 (수정 모드일 때만)
        if st.session_state.expense_edit_id:
            if st.button("🗑️ 이 내역 삭제하기", key="del_exp_btn", type="primary"):
                row = expenses_df[expenses_df['id'] == st.session_state.expense_edit_id].iloc[0]
                is_linked = True if (row['linked_memory_id'] and row['linked_memory_id'] > 0) else False
                confirm_delete_dialog("expense", st.session_state.expense_edit_id, is_linked)

    # -------------------------------------------------------
    # 하단: 지출 내역 테이블 및 그래프
    # -------------------------------------------------------
    st.divider()
    st.subheader("📊 지출 내역")
    st.caption("💡 표의 행을 클릭하면 상단 폼에서 수정하거나 삭제할 수 있습니다.")

    if not expenses_df.empty:
        # 컬럼 존재 여부 체크 (기존 DB 호환)
        if 'search_address' not in expenses_df.columns: expenses_df['search_address'] = ""
        # [수정] 위도/경도 컬럼 체크 (둘 다 체크)
        if 'gemini_lat' not in expenses_df.columns: expenses_df['gemini_lat'] = None
        if 'gemini_lon' not in expenses_df.columns: expenses_df['gemini_lon'] = None
        
        display_df = expenses_df.rename(columns={
            'date': '날짜', 'store_name': '가게명', 'address': '주소(표시)', 
            'category': '카테고리', 
            'price_krw': '환산금액(KRW)', 'linked_memory_id': '연결 추억ID'
            # 'search_address': '주소(검색)',
            # 'gemini_lat', 'gemini_lon'은 표시 안 함
        })
        
        # [수정] 테이블 뷰에서 AI위도/경도 컬럼 제외
        event = st.dataframe(
            display_df[['id', '날짜', '가게명', '주소(표시)', '카테고리', '환산금액(KRW)', '연결 추억ID']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        # 행 클릭 시 수정 모드로 전환
        if event.selection.rows:
            sel_idx = event.selection.rows[0]
            real_id = int(expenses_df.iloc[sel_idx]['id'])
            
            if st.session_state.expense_edit_id != real_id:
                row = expenses_df.iloc[sel_idx]
                
                st.session_state.expense_edit_id = real_id
                st.session_state.form_date = datetime.strptime(row['date'], "%Y-%m-%d")
                st.session_state.form_store = row['store_name']
                st.session_state.form_address = row['address'] if row['address'] else ""
                st.session_state.form_search_address = row['search_address'] if row['search_address'] else ""
                
                # DB에서 값 불러오기
                st.session_state.form_gemini_lat = row['gemini_lat']
                st.session_state.form_gemini_lon = row['gemini_lon']
                
                st.session_state.form_category = row['category']
                st.session_state.form_price = float(row['price_foreign'])
                try: st.session_state.form_linked_mem = int(row['linked_memory_id'])
                except: st.session_state.form_linked_mem = None
                st.rerun()
        
        # 그래프 영역
        c1, c2 = st.columns(2)
        with c1:
            fig_bar = px.bar(display_df, x="날짜", y="환산금액(KRW)", color="카테고리", title="일자별/카테고리별 지출")
            st.plotly_chart(fig_bar, use_container_width=True)
        with c2:
            fig_pie = px.pie(display_df, values="환산금액(KRW)", names="카테고리", title="카테고리별 비중")
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # 내보내기 버튼 영역
        st.subheader("📥 데이터 내보내기")
        d_col1, d_col2, d_col3, empty_space = st.columns([1, 1.075, 1, 6.925])
        
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        d_col1.download_button("📄 CSV 다운로드", data=csv, file_name="Dont_Worry.csv", mime="text/csv", use_container_width=True)
        
        excel_data = to_excel(display_df)
        d_col2.download_button("📊 Excel 다운로드", data=excel_data, file_name="Dont_Worry.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)

        try:
            pdf_data = create_pdf(display_df)
            d_col3.download_button("📕 PDF 다운로드", data=pdf_data, file_name="Dont_Worry.pdf", mime='application/pdf', use_container_width=True)
        except Exception as e:
            d_col3.error(f"PDF 생성 실패: {e}")
    else:
        st.info("아직 저장된 지출 내역이 없습니다.")


# -----------------------------------------------------------------------------
# TAB 2: 추억 지도 (Google Map 스타일)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("📍 나만의 여행 지도")
    m_col1, m_col2 = st.columns([2, 1])

    # --- 지도 표시 영역 (왼쪽) ---
    with m_col1:
        m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)
        
        for idx, row in memories_df.iterrows():
            popup_html = f"""
            <div style="width:200px">
                <b>{row['location_name']}</b><br>
                <small>{row['date']}</small><br>
                <p>{row['comment']}</p>
            """
            if row['image_data']:
                popup_html += f'<img src="data:image/jpeg;base64,{row["image_data"]}" width="100%"><br>'
            if row['linked_expense_id'] and row['linked_expense_id']>0:
                popup_html += f"(Linked Exp: {int(row['linked_expense_id'])})"
            popup_html += "</div>"
            
            marker = folium.Marker(
                [row['lat'], row['lon']],
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=row['location_name'],
                icon=folium.Icon(color='red', icon='heart')
            )
            marker.add_to(m)
        
        st.caption("👇 지도에서 핀을 클릭하면 내용이 표시되고, 빈 곳을 클릭하면 위치가 입력됩니다.")
        map_data = st_folium(m, height=500, use_container_width=True, return_on_hover=False)

    # --- 추억 입력 영역 (오른쪽) ---
    with m_col2:
        st.write("#### 📝 추억 기록/수정")
        
        # [수정 1] 옵션 생성 순서 변경: '(연결 안 함)'을 가장 먼저(0번 인덱스)에 배치
        exp_opts = {"(연결 안 함)": None}
        # 기존 지출 내역 추가
        exp_opts.update({f"{r['id']}: {r['store_name']} ({int(r['price_krw'])}원)": r['id'] for _, r in expenses_df.iterrows()})
        exp_keys = list(exp_opts.keys())
        
        # [수정 2] SelectBox 그리기 전, '기본 선택 값(Index)' 미리 계산
        # -> 수정 모드라면 해당 추억에 연결된 지출을 찾고, 아니면 0번(연결 안 함) 선택
        def_exp_index = 0  # 기본값: 연결 안 함
        
        if st.session_state.memory_edit_id:
            # 현재 수정 중인 추억 데이터 미리 조회
            target_mem = memories_df[memories_df['id'] == st.session_state.memory_edit_id]
            if not target_mem.empty:
                linked_id = target_mem.iloc[0]['linked_expense_id']
                # 연결된 지출 ID가 유효하면 해당 옵션의 인덱스 찾기
                if linked_id and linked_id > 0:
                    try:
                        # value(ID)로 key 찾기
                        found_key = next(k for k, v in exp_opts.items() if v == int(linked_id))
                        def_exp_index = exp_keys.index(found_key)
                    except StopIteration:
                        def_exp_index = 0 # 연결된 지출이 목록에 없으면(삭제됨 등) 기본값

        # [수정 3] 계산된 index를 적용하여 SelectBox 생성
        # 이렇게 하면 앱 재실행 시 무조건 0번(연결 안 함) 혹은 저장된 값으로 초기화됨
        sel_exp_key = st.selectbox(
            "🔗 위치를 확인할 지출 선택", 
            exp_keys, 
            index=def_exp_index, 
            key="mem_link_select"
        ) 
        sel_exp_id = exp_opts[sel_exp_key]

        # --- 아래는 기존 로직과 동일 (API 호출 및 지도 이동) ---
        
        # 선택된 지출이 있고, '이전 선택'과 다를 경우에만 위치 검색 실행
        if sel_exp_id is not None and sel_exp_id != st.session_state.last_sel_exp_id:
            target_exp = expenses_df[expenses_df['id'] == sel_exp_id]
            if not target_exp.empty:
                row = target_exp.iloc[0]
                
                search_addr = row['search_address']
                g_lat = row['gemini_lat']
                g_lon = row['gemini_lon']
                
                coords = None
                source_msg = ""

                # [1순위] Nominatim (정제된 주소로)
                if search_addr and search_addr.strip():
                    st.toast(f"🌏 1차 시도: Nominatim 검색... ({search_addr})")
                    # print(f"🌏 1차 시도: Nominatim 검색... ({search_addr})")
                    coords = get_lat_lon_from_address(search_addr)
                    if coords:
                        source_msg = "Nominatim (정확함)"

                # [2순위] 실패 시 Gemini 추정 좌표 사용 (DB에서)
                if not coords and g_lat is not None and g_lon is not None:
                    try:
                        g_lat = float(g_lat)
                        g_lon = float(g_lon)
                        coords = (g_lat, g_lon)
                        source_msg = "Gemini AI 추정 (대략적)"
                        st.toast(f"🤖 2차 시도: Gemini 추정 좌표 사용")
                    except: pass

                if coords:
                    st.session_state.map_center = [coords[0], coords[1]]
                    st.session_state.map_zoom = 16
                    st.session_state.last_sel_exp_id = sel_exp_id
                    st.success(f"📍 위치 이동 성공! ({source_msg})")
                    st.rerun()
                else:
                    st.error(f"⚠️ 위치 찾기 실패.\n1차: {search_addr} (실패)\n2차: AI 추정 좌표 없음")
            
            # 검색 후 상태 업데이트
            st.session_state.last_sel_exp_id = sel_exp_id
            
        # "연결 안 함" 선택 시 상태 초기화
        if sel_exp_id is None:
            st.session_state.last_sel_exp_id = None
        
        # 지도 인터랙션 (핀 클릭) 처리
        if map_data:
            if map_data['last_object_clicked']:
                clicked_lat = map_data['last_object_clicked']['lat']
                clicked_lng = map_data['last_object_clicked']['lng']
                
                matched_row = memories_df[
                    (memories_df['lat'].round(6) == round(clicked_lat, 6)) & 
                    (memories_df['lon'].round(6) == round(clicked_lng, 6))
                ]
                
                if not matched_row.empty:
                    found_id = int(matched_row.iloc[0]['id'])
                    if st.session_state.memory_edit_id != found_id:
                        st.session_state.memory_edit_id = found_id
                        st.rerun()
            
        # 데이터 준비 (Form 기본값 설정을 위해 다시 읽기 - 위에서 읽었지만 Form 처리를 위해 유지)
        if st.session_state.memory_edit_id is not None:
            st.info(f"✏️ [추억 수정] ID: {st.session_state.memory_edit_id}")
            # 이미 위에서 target_mem을 읽었을 수도 있지만 안전하게 다시 처리하거나 재활용
            edit_mem_row = memories_df[memories_df['id'] == st.session_state.memory_edit_id]
            if not edit_mem_row.empty:
                edit_mem_row = edit_mem_row.iloc[0]
                def_date = datetime.strptime(edit_mem_row['date'], "%Y-%m-%d")
                def_loc = edit_mem_row['location_name']
                def_com = edit_mem_row['comment']
                def_lat = float(edit_mem_row['lat'])
                def_lon = float(edit_mem_row['lon'])
                # def_link는 이미 selectbox에서 처리됨
            else:
                st.session_state.memory_edit_id = None
                st.rerun()
        else:
            # 신규 모드
            def_date = datetime.today()
            def_loc = ""
            def_com = ""
            if map_data and map_data['last_clicked']:
                def_lat = map_data['last_clicked']['lat']
                def_lon = map_data['last_clicked']['lng']
            else:
                def_lat = st.session_state.map_center[0]
                def_lon = st.session_state.map_center[1]
        
        st.caption("위의 지출 선택 박스를 변경하면 해당 위치로 지도가 이동합니다.")

        # --- 입력 폼 ---
        with st.form("memory_form"):
            mem_date = st.date_input("날짜", value=def_date)
            mem_loc = st.text_input("장소명", value=def_loc)
            mem_comment = st.text_area("메모", value=def_com)
            
            c1, c2 = st.columns(2)
            in_lat = c1.number_input("위도", value=def_lat, format="%.6f")
            in_lon = c2.number_input("경도", value=def_lon, format="%.6f")
            
            mem_photo = st.file_uploader("사진", type=['jpg','png','jpeg'])
            
            btn_txt = "💾 수정 저장" if st.session_state.memory_edit_id else "📍 핀 저장"
            
            if st.form_submit_button(btn_txt):
                if mem_loc:
                    # sel_exp_id는 form 외부의 selectbox 값을 사용
                    if st.session_state.memory_edit_id:
                        db.update_memory(
                            st.session_state.memory_edit_id,
                            mem_date.strftime("%Y-%m-%d"), mem_loc, mem_comment, 
                            in_lat, in_lon, mem_photo, sel_exp_id
                        )
                        st.success("수정 완료")
                        st.session_state.memory_edit_id = None
                    else:
                        db.save_memory(
                            mem_date.strftime("%Y-%m-%d"), mem_loc, mem_comment, 
                            in_lat, in_lon, mem_photo, sel_exp_id
                        )
                        st.success("저장 완료")
                    st.rerun()
                else:
                    st.error("장소명을 입력하세요.")
        
        # 삭제 버튼
        if st.session_state.memory_edit_id:
            if st.button("🗑️ 삭제하기", key="del_mem_btn", type="primary"):
                 # (기존 삭제 로직 유지)
                row = memories_df[memories_df['id'] == st.session_state.memory_edit_id].iloc[0]
                is_linked = True if (row['linked_expense_id'] and row['linked_expense_id'] > 0) else False
                confirm_delete_dialog("memory", st.session_state.memory_edit_id, is_linked)    
    # --- 하단: 추억 리스트 ---
    st.divider()
    st.subheader("📒 추억 목록 관리")
    
    if not memories_df.empty:
        disp_mem = memories_df.rename(columns={'id': 'ID', 'date': '날짜', 'location_name': '장소', 'comment': '메모', 'linked_expense_id': '연결된지출ID'})
        mem_event = st.dataframe(
            disp_mem[['ID', '날짜', '장소', '메모', '연결된지출ID']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        if mem_event.selection.rows:
            sel_idx = mem_event.selection.rows[0]
            real_mem_id = int(memories_df.iloc[sel_idx]['id'])
            
            if st.session_state.memory_edit_id != real_mem_id:
                st.session_state.memory_edit_id = real_mem_id
                sel_row = memories_df.iloc[sel_idx]
                st.session_state.map_center = [sel_row['lat'], sel_row['lon']]
                st.session_state.map_zoom = 16
                st.rerun()
    else:
        st.info("저장된 추억이 없습니다.")