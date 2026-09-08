# -*- coding: utf-8 -*-
import os, glob, json
from datetime import datetime
from openpyxl import Workbook
from google import genai
from google.genai import types

# 1. 기준 원자재 단가 (KRW/kg) 및 판정 기준
RAW_MATERIAL_PRICES = {
    "steel": 1200,      # 철/환봉/샤프트
    "aluminum": 3500,   # 알루미늄
    "copper": 13000,    # 구리/코일
    "sus": 4200         # 스테인리스
}
STD_PROCESSING_FEE = 800    # 표준 가공비 (원)
STD_OVERHEAD_FEE = 300      # 일반관리비 (원)
ACCEPTABLE_VARIANCE = 0.10  # +10% 초과 시 재협상 판정

INPUT_DIR = "./input_quotes"
OUTPUT_DIR = "./output_reports"

# 2. 비전 모델을 통한 비정형 견적서 파싱
def extract_quote_from_image(client: genai.Client, image_path: str) -> list:
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    if ext == ".pdf": mime = "application/pdf"

    prompt = """
    당신은 기업 구매/원가관리 전문가입니다.
    견적서 이미지에서 각 품목별 견적 내역을 정확히 추출하여 JSON 배열 포맷으로만 응답하세요.
    [추출 필드]: part_name, material('steel','aluminum','copper','sus','other'), 
                 weight_kg, qty, quoted_unit_price, supplier_name
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Part.from_bytes(data=img_bytes, mime_type=mime), prompt]
    )
    # JSON 파싱 및 데이터 반환
    clean_text = response.text.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

# 3. 타당성 판정 및 엑셀 저장 (전체 코드는 첨부 파일 참조)
