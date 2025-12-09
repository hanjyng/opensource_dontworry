import pandas as pd
import io


# ==========================================
# 함수: 엑셀 다운로드용 바이너리 생성
# ==========================================
def to_excel(df):
    """
    엑셀 다운로드용 바이너리 생성 
    """
    output = io.BytesIO()
    # xlsxwriter 엔진 사용
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
        # (선택사항) 엑셀 컬럼 너비 자동 조정 등의 꾸미기 가능
    processed_data = output.getvalue()
    return processed_data

# 이 파일을 직접 실행했을 때만 초기화 테스트 진행
if __name__ == "__main__":
    to_excel()
    print(f"to_excel() {to_excel}")
