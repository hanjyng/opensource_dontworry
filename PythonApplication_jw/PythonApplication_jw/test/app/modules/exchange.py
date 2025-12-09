import yfinance as yf
import streamlit as st
from datetime import datetime, timedelta

@st.cache_data(ttl=3600)
def get_exchange_rate(target_currency, target_date=None):
    """
    [최적화 버전] 환율 조회 함수
    - 직거래(KRW)와 달러경유(USD Cross Rate) 데이터를 모두 조회합니다.
    - 두 방식 중 '선택한 날짜(target_date)'에 더 가까운 데이터를 자동으로 채택합니다.
    """
    if target_currency == "KRW": return 1.0

    # 기준 날짜 설정 (미래/오늘이면 현재, 아니면 지정 날짜)
    if target_date is None or target_date >= datetime.today().date():
        target_date = datetime.today().date()
        is_current = True
    else:
        is_current = False

    # ---------------------------------------------------------
    # 내부 헬퍼: (날짜, 환율) 튜플을 반환
    # ---------------------------------------------------------
    def fetch_rate_with_date(ticker_symbol):
        try:
            ticker = yf.Ticker(ticker_symbol)
            if is_current:
                # 최신 데이터 1일치
                df = ticker.history(period="1d")
            else:
                # 과거 데이터 (휴일 고려 7일 범위)
                start_date = target_date - timedelta(days=7)
                end_date = target_date + timedelta(days=1)
                df = ticker.history(start=start_date, end=end_date)
            
            if not df.empty:
                last_row = df.iloc[-1]
                # (데이터의 실제 날짜, 종가) 반환
                # yfinance 날짜는 datetime 형식이므로 .date()로 변환
                return last_row.name.date(), last_row['Close']
            return None, None
        except Exception as e:
            # print(f"Error fetching {ticker_symbol}: {e}")
            return None, None
    # ---------------------------------------------------------

    # 1. [직거래] 데이터 조회 (예: VNDKRW=X)
    date_direct, val_direct = fetch_rate_with_date(f"{target_currency}KRW=X")

    # 2. [달러 경유] 데이터 조회 (예: USDKRW=X, VND=X)
    date_usdkrw, val_usdkrw = fetch_rate_with_date("USDKRW=X")
    date_targetusd, val_targetusd = fetch_rate_with_date(f"{target_currency}=X")

    # 경유 환율 계산 (둘 다 존재해야 함)
    val_cross = None
    date_cross = None
    
    if val_usdkrw and val_targetusd:
        val_cross = val_usdkrw / val_targetusd
        # 두 데이터 중 더 오래된 날짜를 기준으로 삼음 (보수적 접근)
        # 혹은 둘 중 target_date와 먼 날짜를 기준으로 하여 패널티를 줌
        if abs((target_date - date_usdkrw).days) > abs((target_date - date_targetusd).days):
            date_cross = date_usdkrw
        else:
            date_cross = date_targetusd

    # ---------------------------------------------------------
    # 3. [최종 결정] 날짜 경쟁 (Race)
    # ---------------------------------------------------------
    
    # Case A: 둘 다 실패
    if val_direct is None and val_cross is None:
        return None

    # Case B: 직거래만 성공
    if val_direct is not None and val_cross is None:
        return round(val_direct, 4)

    # Case C: 경유만 성공
    if val_direct is None and val_cross is not None:
        return round(val_cross, 4)

    # Case D: 둘 다 성공 -> "누가 더 목표 날짜에 가까운가?"
    diff_direct = abs((target_date - date_direct).days)
    diff_cross = abs((target_date - date_cross).days)

    print(f"[{target_currency}] Direct Gap: {diff_direct} days vs Cross Gap: {diff_cross} days")

    if diff_direct <= diff_cross:
        # 직거래가 날짜가 더 가깝거나 같으면 우선 (직거래 선호)
        return round(val_direct, 4)
    else:
        # 경유 데이터가 더 최신(목표 날짜에 가까움)이면 선택
        return round(val_cross, 4)

if __name__ == "__main__":
    # 테스트
    t_date = datetime(2023, 9, 25).date() # 과거 날짜 예시
    print(f"Result: {get_exchange_rate('VND', t_date)}")
# import yfinance as yf
# import streamlit as st
# from datetime import datetime, timedelta


# @st.cache_data(ttl=3600)
# def get_exchange_rate(target_currency, target_date=None):
#     if target_currency == "KRW": return 1.0
#     ticker_symbol = f"{target_currency}KRW=X"
#     try:
#         ticker = yf.Ticker(ticker_symbol)
#         if target_date is None or target_date >= datetime.today().date():
#             data = ticker.history(period="1d")
#         else:
#             start_date = target_date - timedelta(days=7)
#             end_date = target_date + timedelta(days=1)
#             data = ticker.history(start=start_date, end=end_date)
#         if not data.empty:
#             return round(data['Close'].iloc[-1], 4)
#         else:
#             return None
#     except Exception as e:
#         print(f"get_exchange_rate(): {e}")
#         return None


# if __name__ == "__main__":
#     get_exchange_rate()
#     print(f"gemini - analyze_receipt()")