import sqlite3
import pandas as pd
import os

# CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) # .../project/modules
# ROOT_DIR = os.path.dirname(CURRENT_DIR)                  # .../project
# 파일 경로를 현재 스크립트 위치 기준으로 절대 경로로 잡는 것이 안전합니다.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(ROOT_DIR, "Don't ₩orry.db") 

def init_db():
    """데이터베이스와 테이블을 초기화합니다."""
    # with 문을 사용하여 connection 관리를 자동으로 처리
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                store_name TEXT,
                category TEXT,
                price_foreign REAL,
                currency TEXT,
                price_krw INTEGER,
                exchange_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # commit은 with 문을 빠져나갈 때 자동으로 수행되지만, 명시적으로 적어도 무방합니다.
        conn.commit() 

def save_expense(date, store, category, price_f, currency, price_k, rate):
    """지출 내역을 DB에 저장합니다."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO expenses (date, store_name, category, price_foreign, currency, price_krw, exchange_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, store, category, price_f, currency, price_k, rate))
        conn.commit()

def load_expenses():
    """DB에서 모든 지출 내역을 불러와 DataFrame으로 반환합니다."""
    with sqlite3.connect(DB_NAME) as conn:
        # pandas read_sql은 내부적으로 커넥션을 잘 처리하지만, context manager 안에서 쓰는 것이 안전
        df = pd.read_sql("SELECT * FROM expenses ORDER BY date DESC", conn)
    return df

# 이 파일을 직접 실행했을 때만 초기화 테스트 진행
if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_NAME}")