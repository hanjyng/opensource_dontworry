from fpdf import FPDF
import streamlit as st
import os


# ==========================================
# 함수: PDF 다운로드용 바이너리 생성
# ==========================================
def create_pdf(df):
    
    # [수정 1] 용지를 '가로(L)'로 설정하여 너비를 확보 (A4 가로 너비 약 297mm)
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    # pdf = FPDF()
    pdf.add_page()
    
    # 1. 현재 파일(to_pdf.py)의 위치: .../app/modules
    modules_dir = os.path.dirname(os.path.abspath(__file__))
    # 2. 프로젝트 루트(app) 위치: .../app
    app_dir = os.path.dirname(modules_dir)
    # [중요] 한글 폰트 설정 (폰트 파일이 같은 경로에 있어야 함)
    # font_path = "../fonts/NanumGothic/NanumGothic-Regular.ttf"  # 폰트 파일명
    font_path = os.path.join(app_dir, "fonts", "NanumGothic", "NanumGothic-Regular.ttf")
    
    # 디버깅용 출력 (터미널에서 확인 가능)
    print(f"🔎 폰트 찾는 경로: {font_path}")
    print(f"font_path: {font_path}")
    
    # 폰트 파일이 있는지 확인
    if os.path.exists(font_path):
        # fpdf2 최신 버전에서는 fname 인자 사용 권장
        # pdf.add_font("NanumGothic", "", font_path)
        pdf.add_font(family="NanumGothic", fname=font_path)
        pdf.set_font("NanumGothic", size=10)
    else:
        # 폰트가 없으면 기본 폰트 사용 (한글 깨짐 주의)
        pdf.set_font("Arial", size=10)
        st.toast("⚠️ NanumGothic 폰트 파일이 없어 한글이 깨질 수 있습니다.", icon="⚠️")

    # 제목
    pdf.set_font(size=16)
    pdf.cell(200, 10, txt="Travel Expense Report", ln=True, align='C')
    pdf.ln(10)

    # ---------------------------------------------------------
    # [수정 2] 컬럼별 너비 최적화 (가로 모드 기준, 합계 약 270~280mm 권장)
    # ---------------------------------------------------------
    # 데이터프레임의 컬럼 이름에 맞춰 너비를 지정해줍니다.
    # 지정하지 않은 컬럼은 기본값(default_width)을 씁니다.
    width_map = {
        'id': 10,
        '날짜': 25,
        '가게명': 50,      # 가게 이름은 길 수 있으니 넉넉하게
        '카테고리': 20,
        '현지 금액': 25,
        '통화': 15,
        '환산금액(KRW)': 35,
        '적용환율': 25,
        'created_at': 40,  # 시간은 기니까 넓게
    }
    default_width = 30 # 위 목록에 없는 컬럼의 기본 너비

    # 헤더 높이 설정
    line_height = 8

    # 테이블 헤더
    pdf.set_font(size=10)
    cols = df.columns.tolist()
    
    # 간단한 테이블 그리기
    # 너비 설정 (A4 가로폭 약 190mm 배분)
    # col_width = 190 / len(cols)
    
    # 헤더 출력
    for col in cols:
        # pdf.cell(col_width, 10, str(col), border=1, align='C')
        # 설정된 너비 가져오기 (없으면 기본값)
        w = width_map.get(col, default_width)
        # 헤더 그리기 (fill=True는 배경색 채우기)
        pdf.cell(w, line_height, str(col), border=1, align='C') #, fill=True)
    pdf.ln()

    # 데이터 출력
    for i in range(len(df)):
        for col in cols:
            # 데이터가 너무 길면 잘라내기
            # text = str(df.iloc[i][col])
            # pdf.cell(col_width, 10, text, border=1, align='C')
            
            w = width_map.get(col, default_width)
            
            # 데이터 가져오기 및 문자열 변환
            raw_text = str(df.iloc[i][col])
            
            # (선택 사항) created_at 처럼 너무 긴 데이터는 잘라내기
            if col == 'created_at' and len(raw_text) > 19:
                raw_text = raw_text[:19] # 초 단위까지만 표시
            pdf.cell(w, line_height, raw_text, border=1, align='C')
        pdf.ln()

    # return pdf.output(dest='S').encode('latin-1')
    # [수정] fpdf2 최신 버전 호환성 (bytes로 변환)
    return bytes(pdf.output())

# 이 파일을 직접 실행했을 때만 초기화 테스트 진행
if __name__ == "__main__":
    # create_pdf()
    # print(f"create_pdf() {create_pdf}")
    
    # 테스트용 더미 데이터
    import pandas as pd
    data = {'날짜': ['2024-05-01'], '가게명': ['테스트식당'], '금액': [10000]}
    df = pd.DataFrame(data)
    
    result = create_pdf(df)
    print(f"PDF 생성 완료 (크기: {len(result)} bytes)")
