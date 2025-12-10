import yfinance as yf
import streamlit as st
from datetime import datetime, timedelta

@st.cache_data(ttl=3600)
def get_exchange_rate(target_currency, target_date=None):
    """
    환율 조회 함수 (최종 수정 버전)
    1. Chained Fetching: 타국 통화 데이터 날짜를 기준으로 원화 환율을 조회하여 시점 불일치 해결
    2. Cross Rate Logic: EUR, GBP 등 역환율(Indirect Quote) 통화에 대한 곱셈/나눗셈 분기 처리 적용
    """
    if target_currency == "KRW": return 1.0

    # 0. 기준 날짜 설정
    # 입력 날짜가 없거나 미래라면 오늘 날짜로 고정
    if target_date is None or target_date >= datetime.today().date():
        search_base_date = datetime.today().date()
    else:
        search_base_date = target_date

    # =========================================================
    # [Helper Function] 특정 날짜 기준으로 가장 가까운 과거 데이터 가져오기
    # =========================================================
    def fetch_closest_data(ticker_symbol, ref_date):
        try:
            ticker = yf.Ticker(ticker_symbol)
            
            # 오늘 날짜 기준인 경우 (빠른 조회)
            if ref_date >= datetime.today().date():
                df = ticker.history(period="1d")
            else:
                # 과거 데이터 조회 (휴일 고려 앞뒤 여유 둠, 보통 과거 7일)
                start_dt = ref_date - timedelta(days=7)
                end_dt = ref_date + timedelta(days=1)
                df = ticker.history(start=start_dt, end=end_dt)
            
            if not df.empty:
                # 날짜 오름차순 정렬되어 있으므로 마지막 행이 기준일에 가장 가까운 과거 데이터
                last_row = df.iloc[-1]
                found_date = last_row.name.date()
                return found_date, float(last_row['Close'])
            
            return None, None
        except Exception as e:
            # print(f"Error fetching {ticker_symbol}: {e}")
            return None, None

    # =========================================================
    # 1. [Direct] 직거래 환율 조회 (예: VNDKRW=X)
    # =========================================================
    date_direct, rate_direct = fetch_closest_data(f"{target_currency}KRW=X", search_base_date)

    # =========================================================
    # 2. [Cross] 달러 경유 환율 조회 (Logic 분기 및 Chained Fetching)
    # =========================================================
    date_cross = None
    rate_cross = None

    # 2-1. 타국 화폐 -> 달러 환율 조회 (Leg 1)
    # 예: JPY=X (달러당 엔), EUR=X (유로당 달러)
    date_leg1, rate_leg1 = fetch_closest_data(f"{target_currency}=X", search_base_date)

    if date_leg1 and rate_leg1:
        # [핵심 1: Chained Fetching]
        # 타국 화폐 데이터가 발견된 날짜(date_leg1)를 기준으로 달러-원 환율을 조회합니다.
        # 이렇게 해야 "엔화는 10일 치, 원화는 17일 치"를 가져와서 계산하는 오류를 막습니다.
        date_leg2, rate_leg2_usdkrw = fetch_closest_data("USDKRW=X", date_leg1)
        
        if date_leg2 and rate_leg2_usdkrw:
            # 날짜 동기화 확인 (3일 이내 차이면 유효하다고 판단)
            sync_gap = abs((date_leg1 - date_leg2).days)
            
            if sync_gap <= 3:
                # [핵심 2: 통화별 수식 분기]
                # USD가 기준(Base)이 아닌 통화들 (EUR, GBP, AUD, NZD 등)
                # 이들은 1.05 (USD/EUR) 처럼 나오므로 KRW/USD * USD/EUR = KRW/EUR가 되어야 함 (곱하기)
                inverse_currencies = ["EUR", "GBP", "AUD", "NZD"]
                
                if target_currency in inverse_currencies:
                    # 공식: (원/달러) * (달러/유로) = 원/유로
                    rate_cross = rate_leg2_usdkrw * rate_leg1
                else:
                    # 일반적인 아시아 통화 (JPY, VND, CNY 등)
                    # 이들은 150 (JPY/USD) 처럼 나오므로 (원/달러) / (엔/달러) = 원/엔 (나누기)
                    rate_cross = rate_leg2_usdkrw / rate_leg1
                
                date_cross = date_leg1 # 최종 날짜는 타국 화폐 기준일

    # =========================================================
    # 3. [최종 결정] Direct vs Cross 경쟁
    # =========================================================
    
    # 둘 다 실패
    if rate_direct is None and rate_cross is None:
        return None

    # 하나만 성공
    if rate_direct is not None and rate_cross is None: return round(rate_direct, 4)
    if rate_direct is None and rate_cross is not None: return round(rate_cross, 4)

    # 둘 다 성공 -> 사용자가 원했던 'search_base_date'와 시간차가 적은 데이터 선택
    diff_direct = abs((search_base_date - date_direct).days)
    diff_cross = abs((search_base_date - date_cross).days)

    if diff_direct <= diff_cross:
        return round(rate_direct, 4)
    else:
        return round(rate_cross, 4)

if __name__ == "__main__":
    # 테스트 코드
    print(f"JPY Test: {get_exchange_rate('JPY')}") # 나누기 로직 확인
    print(f"EUR Test: {get_exchange_rate('EUR')}") # 곱하기 로직 확인