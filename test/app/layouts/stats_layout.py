import streamlit as st
import plotly.express as px

from modules.sqlite3_db import init_db, save_expense, load_expenses
from modules.to_excel import to_excel
from modules.to_pdf import create_pdf


def show_stats_section():
    """
    통계 및 데이터 내보내기 섹션을 렌더링하는 함수
    """

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
        
        # -------------------------------------------------------
        # [추가] 다운로드 버튼 영역 (CSV / Excel / PDF)
        # -------------------------------------------------------
        st.subheader("📥 데이터 내보내기")
        
        # 기존: 3등분이라 너무 멀어짐
        # d_col1, d_col2, d_col3 = st.columns(3) 
        # 수정: 1 : 1 : 1 비율로 버튼 자리를 만들고, 나머지(7)는 빈 공간으로 둠
        d_col1, d_col2, d_col3, empty_space = st.columns([1, 1.075, 1, 6.925])
        
        # CSV 다운로드 기능 (DB 데이터를 기반으로 생성)
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        # st.download_button("CSV 다운로드", csv, "Don't ₩orry.csv", "text/csv")
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