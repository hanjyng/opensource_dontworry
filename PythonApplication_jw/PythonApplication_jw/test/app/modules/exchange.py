import yfinance as yf
import streamlit as st
from datetime import datetime, timedelta


@st.cache_data(ttl=3600)
def get_exchange_rate(target_currency, target_date=None):
    if target_currency == "KRW": return 1.0
    ticker_symbol = f"{target_currency}KRW=X"
    try:
        ticker = yf.Ticker(ticker_symbol)
        if target_date is None or target_date >= datetime.today().date():
            data = ticker.history(period="1d")
        else:
            start_date = target_date - timedelta(days=7)
            end_date = target_date + timedelta(days=1)
            data = ticker.history(start=start_date, end=end_date)
        if not data.empty:
            return round(data['Close'].iloc[-1], 4)
        else:
            return None
    except Exception as e:
        print(f"get_exchange_rate(): {e}")
        return None


if __name__ == "__main__":
    get_exchange_rate()
    print(f"gemini - analyze_receipt()")