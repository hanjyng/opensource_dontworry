import sqlite3
import base64 # 이미지를 DB에 저장하기 위해 필요 (간단한 프로젝트용)
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
        
        # 지출 테이블
        c.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                store_name TEXT,
                address TEXT,
                search_address TEXT,  -- [추가] 검색용 주소 컬럼
                gemini_lat REAL,    -- [추가] Gemini가 추정한 위도
                gemini_lon REAL,    -- [추가] Gemini가 추정한 경도
                category TEXT,
                price_foreign REAL,
                currency TEXT,
                price_krw INTEGER,
                exchange_rate REAL,
                linked_memory_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 추억 테이블
        # lat: 위도, lon: 경도, image_data: 사진(Base64 문자열)
        c.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                location_name TEXT,
                comment TEXT,
                lat REAL,
                lon REAL,
                image_data TEXT,
                linked_expense_id INTEGER
            )
        ''')
        
        # [마이그레이션] 컬럼 추가 시도
        try: c.execute("ALTER TABLE expenses ADD COLUMN address TEXT")
        except: pass
        try: c.execute("ALTER TABLE expenses ADD COLUMN search_address TEXT")
        except: pass
        try: c.execute("ALTER TABLE expenses ADD COLUMN gemini_lat REAL")
        except: pass
        try: c.execute("ALTER TABLE expenses ADD COLUMN gemini_lon REAL")
        except: pass
        try: c.execute("ALTER TABLE expenses ADD COLUMN linked_memory_id INTEGER")
        except: pass
        try: c.execute("ALTER TABLE memories ADD COLUMN linked_expense_id INTEGER")
        except: pass
        
        # commit은 with 문을 빠져나갈 때 자동으로 수행되지만, 명시적으로 적어도 무방합니다.
        conn.commit() 

# ==========================================
# 공통: 1대1 연결 로직
# ==========================================
def update_linkage(expense_id, memory_id):
    """
    지출(expense_id)과 추억(memory_id)을 1:1로 연결합니다.
    - 기존 연결은 끊고(NULL), 새로운 연결을 맺습니다.
    - 둘 중 하나가 None이면 연결 해제 로직으로 작동합니다.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    try:
        # 1. 기존 연결 정리 (Expense 입장에서)
        if expense_id is not None:
            # 이 지출이 원래 가리키던 추억이 있다면, 그 추억의 링크 해제
            c.execute("UPDATE memories SET linked_expense_id = NULL WHERE linked_expense_id = ?", (expense_id,))
            # 이 지출을 가리키던 다른 추억들의 링크도 해제 (1:1 유지)
            c.execute("UPDATE memories SET linked_expense_id = NULL WHERE linked_expense_id = ?", (expense_id,))

        # 2. 기존 연결 정리 (Memory 입장에서)
        if memory_id is not None:
            # 이 추억이 원래 가리키던 지출이 있다면, 그 지출의 링크 해제
            c.execute("UPDATE expenses SET linked_memory_id = NULL WHERE linked_memory_id = ?", (memory_id,))
            # 이 추억을 가리키던 다른 지출들의 링크도 해제
            c.execute("UPDATE expenses SET linked_memory_id = NULL WHERE linked_memory_id = ?", (memory_id,))

        # 3. 새로운 상호 연결
        if expense_id is not None and memory_id is not None:
            c.execute("UPDATE expenses SET linked_memory_id = ? WHERE id = ?", (memory_id, expense_id))
            c.execute("UPDATE memories SET linked_expense_id = ? WHERE id = ?", (expense_id, memory_id))
        
        # 4. 한쪽만 있는 경우 (연결 해제)
        elif expense_id is not None and memory_id is None:
            c.execute("UPDATE expenses SET linked_memory_id = NULL WHERE id = ?", (expense_id,))
        elif memory_id is not None and expense_id is None:
            c.execute("UPDATE memories SET linked_expense_id = NULL WHERE id = ?", (memory_id,))

        conn.commit()
    except Exception as e:
        print(f"Linkage Error: {e}")
    finally:
        conn.close()

# ==========================================
# 지출 관리(tab)에서 사용할 함수들 
# ==========================================
def save_expense(date, store, address, search_address, g_lat, g_lon, category, price_f, currency, price_k, rate, linked_mem_id):
    """지출 내역을 DB에 저장합니다."""
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO expenses (date, store_name, address, search_address, gemini_lat, gemini_lon, category, price_foreign, currency, price_krw, exchange_rate, linked_memory_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, store, address, search_address, g_lat, g_lon, category, price_f, currency, price_k, rate, linked_mem_id))
        new_id = c.lastrowid
        conn.commit()
        
    # 연결 정보가 있다면 동기화
    if linked_mem_id:
        update_linkage(new_id, linked_mem_id)

def load_expenses():
    """DB에서 모든 지출 내역을 불러와 DataFrame으로 반환합니다."""
    with sqlite3.connect(DB_NAME) as conn:
        # pandas read_sql은 내부적으로 커넥션을 잘 처리하지만, context manager 안에서 쓰는 것이 안전
        df = pd.read_sql("SELECT * FROM expenses ORDER BY date DESC", conn)
    return df

def update_expense(expense_id, date, store, address, search_address, g_lat, g_lon, category, price_f, currency, price_k, rate, linked_mem_id=None):
    "지출 데이터 갱신 함수"
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE expenses 
            SET date=?, store_name=?, address=?, search_address=?, 
            gemini_lat=?, gemini_lon=?, category=?, price_foreign=?, 
            currency=?, price_krw=?, exchange_rate=?, linked_memory_id=?
            WHERE id=?
        ''', (date, store, address, search_address, g_lat, g_lon, category, price_f, currency, price_k, rate, linked_mem_id, expense_id))
        conn.commit()
    
    # 연결 정보 동기화 (None이면 연결 해제됨)
    update_linkage(expense_id, linked_mem_id)

def delete_expense(expense_id):
    "지출 삭제 시 참조하던 추억의 링크도 NULL로 변경"
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        
        # 1. 나를 참조하는 메모리의 링크 끊기
        c.execute("UPDATE memories SET linked_expense_id = NULL WHERE linked_expense_id = ?", (expense_id,))
        
        # 2. 삭제
        c.execute('DELETE FROM expenses WHERE id=?', (expense_id,))
        conn.commit()

# ==========================================
# 추억 지도(tab)에서 사용할 함수들
# ==========================================
def save_memory(date, location_name, comment, lat, lon, image_file, linked_exp_id=None):
    "추억 저장 함수"
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 이미지를 Base64 문자열로 변환 (DB에 직접 저장)
    image_b64 = ""
    if image_file is not None:
        try:
            # 파일 포인터를 처음으로 되돌림 (혹시 앞서 읽었을 경우 대비)
            image_file.seek(0)
            image_bytes = image_file.read()
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        except Exception as e:
            print(f"이미지 변환 오류: {e}")

    c.execute('''
        INSERT INTO memories (date, location_name, comment, lat, lon, image_data, linked_expense_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (date, location_name, comment, lat, lon, image_b64, linked_exp_id))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # 양방향 연결을 확실히 하기 위해 호출 (Expenses 테이블 쪽도 업데이트)
    if linked_exp_id:
        update_linkage(linked_exp_id, new_id)

def load_memories():
    "추억 불러오기 함수"
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql("SELECT * FROM memories ORDER BY date DESC", conn)
    return df

def update_memory(id, date, location, comment, lat, lon, image_file=None, linked_exp_id=None):
    """
    ID를 기준으로 추억 데이터를 수정합니다.
    image_file이 있으면 이미지를 교체하고, 없으면 기존 이미지를 유지합니다.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # 1. 새 이미지가 있는 경우 -> 이미지 포함 전체 업데이트
    if image_file is not None:
        img_bytes = image_file.read()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        c.execute('''
            UPDATE memories 
            SET date=?, location_name=?, comment=?, lat=?, lon=?, image_data=?
            WHERE id=?
        ''', (date, location, comment, lat, lon, img_base64, id))
        
    # 2. 새 이미지가 없는 경우 -> 이미지 제외 업데이트
    else:
        c.execute('''
            UPDATE memories 
            SET date=?, location_name=?, comment=?, lat=?, lon=?
            WHERE id=?
        ''', (date, location, comment, lat, lon, id))
        
    conn.commit()
    conn.close()
    
    update_linkage(linked_exp_id, id)

def delete_memory(id):
    """추억 삭제 시 참조하던 지출의 링크도 NULL로 변경"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # 1. 나를 참조하는 지출의 링크 끊기
    c.execute("UPDATE expenses SET linked_memory_id = NULL WHERE linked_memory_id = ?", (id,))
    
    # 2. 삭제
    c.execute("DELETE FROM memories WHERE id=?", (id,))
    
    conn.commit()
    conn.close()

# 이 파일을 직접 실행했을 때만 초기화 테스트 진행
if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_NAME}")
