import google.generativeai as genai
import streamlit as st
import json


# ==========================================
# [기능] Gemini AI & 환율 (기존 동일)
# ==========================================
def analyze_receipt(image, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash') # 모델명 최신화 권장
        
        prompt = """
        Analyze this receipt image and extract the following information in JSON format:
        
        1. date (format: YYYY-MM-DD, if not found use today)
        2. store_name (name of the shop or restaurant)
        3. address (Return the full original address found on the receipt for display purposes; if no address is found, return an empty string.)
        4. search_address (A simplified address optimized for OpenStreetMap/Google Maps geocoding. 
            - Remove building names, floor numbers (e.g., 4F, 101호), unit numbers, and zip codes if they confuse the search.
            - Keep only the administrative region (City, District) and street name/number.
            - Example (Japan): "新宿区新宿3丁目9-5 ゴールドビル4F" -> "新宿区新宿3丁目9-5"
            - Example (Vietnam): "123 Đường Lê Lợi, Bến Thành, Quận 1, Hồ Chí Minh 70000" -> "123 Đường Lê Lợi, Bến Thành, Quận 1, Hồ Chí Minh"
            - If accurate extraction is impossible, copy the value from 'address'.)
        5. price (total amount, number only, no currency symbol)
        6. category (Choose one strictly from: 식비, 쇼핑, 관광, 교통, 숙박, 기타)
        7. estimated_lat (Estimate the latitude of this location based on the address or store name. If unknown, return null.)
        8. estimated_lon (Estimate the longitude of this location. If unknown, return null.)

        Return ONLY the JSON string. Do not use Markdown code blocks.
        Example: {"date": "2024-01-01", "store_name": "Starbucks", "address": "123 Main St, Seoul", "price": 15.50, "category": "식비"}
        """
        
        # 이미지와 프롬프트를 함께 전송
        response = model.generate_content([prompt, image])
        
        # 응답 텍스트에서 JSON 추출 (가끔 ```json ... ``` 이렇게 줄 때가 있어서 처리)
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        
        return data
    except Exception as e:
        st.error(f"AI 분석 오류: {e}")
        
        return None
    
    
if __name__ == "__main__":
    analyze_receipt()
    print(f"gemini - analyze_receipt()")