# -*- coding: utf-8 -*-
"""
자동 견적 타당성 검토 시스템 (Quotation Auto-Evaluator)
- 작동 방식: 'input_quotes' 폴더에 견적서 이미지(JPG, PNG, PDF)를 넣고 스크립트를 실행하면,
  비전 OCR/LLM API를 통해 품명, 규격, 중량, 단가를 자동 파싱하고
  기준 원가 DB와 비교하여 'output_reports' 폴더에 종합 엑셀 리포트를 생성합니다.
"""

import os
import glob
import json
import base64
import pandas as pd
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. 설정 및 기준 단가 마스터 (Standard Master Data)
# ---------------------------------------------------------
# 원자재 기준 단가 (KRW/kg) - 필요에 따라 갱신
RAW_MATERIAL_PRICES = {
    "steel": 1200,       # 철 / 강재 / 환봉
    "aluminum": 3500,    # 알루미늄
    "copper": 13000,     # 구리 / 동
    "sus": 4200,         # 스테인리스강 (SUS304 등)
}

# 공정 및 판정 기준치
STD_PROCESSING_FEE = 800     # 표준 가공비 (원/EA)
STD_OVERHEAD_FEE = 300       # 고정 일반관리비/마진 (원/EA)
ACCEPTABLE_VARIANCE = 0.10   # ±10% 이내 적정

INPUT_DIR = "./input_quotes"
OUTPUT_DIR = "./output_reports"

# ---------------------------------------------------------
# 2. 견적서 이미지 파싱 (Gemini Vision API 연동)
# ---------------------------------------------------------
def extract_quote_from_image(client: genai.Client, image_path: str) -> list:
    """견적서 이미지에서 품목 리스트를 JSON 형태로 정형화 추출"""
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    # 이미지 확장자에 따른 MIME 타입
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    if ext == ".pdf":
        mime = "application/pdf"

    prompt = """
    당신은 기업 구매/원가관리 전문가입니다.
    제공된 견적서 이미지에서 각 품목별 견적 내역을 정확히 추출하여 오직 JSON 배열 포맷으로만 응답하세요.
    마크다운 코드블록(```json 등) 없이 순수 JSON 텍스트만 출력하세요.

    [추출 필수 필드]:
    - part_name: 품목명 (문자열)
    - material: 주원자재 재질 ('steel', 'aluminum', 'copper', 'sus', 'other' 중 하나로 분류)
    - weight_kg: 단품 중량 (kg 단위 실수, 견적서에 없거나 미표기시 0.0)
    - qty: 수량 (정수)
    - quoted_unit_price: 협력사 제출 단가 (원 단위 숫자, 부가세 별도 공급가액 기준)
    - supplier_name: 견적 발행업체명 (문자열)
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type=mime),
                prompt
            ]
        )
        text_resp = response.text.strip()
        # Clean markdown codeblocks if present
        if text_resp.startswith("```"):
            lines = text_resp.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text_resp = "\n".join(lines).strip()
            
        data = json.loads(text_resp)
        return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f"[-] {image_path} 파싱 실패: {e}")
        return []

# ---------------------------------------------------------
# 3. 원가 분석 및 타당성 판정 엔진
# ---------------------------------------------------------
def evaluate_items(parsed_items: list, file_name: str) -> list:
    evaluated = []
    for item in parsed_items:
        mat = str(item.get("material", "other")).lower().strip()
        weight = float(item.get("weight_kg", 0.0) or 0.0)
        quote = float(item.get("quoted_unit_price", 0.0) or 0.0)
        supplier = item.get("supplier_name", "미상")
        part_name = item.get("part_name", "미상")

        unit_raw_price = RAW_MATERIAL_PRICES.get(mat, 0)
        
        # 중량 정보가 있는 경우 이론 원가 산정
        if unit_raw_price > 0 and weight > 0:
            mat_cost = unit_raw_price * weight
            target_cost = mat_cost + STD_PROCESSING_FEE + STD_OVERHEAD_FEE
            variance = (quote - target_cost) / target_cost
            
            if variance > ACCEPTABLE_VARIANCE:
                judgment = "🔴 [재협상 필요 / 과다]"
                note = f"목표원가 대비 +{variance*100:.1f}% 초과 (가공비/마진 소명 필요)"
            elif variance < -0.15:
                judgment = "🟡 [주의 / 원가부족 확인]"
                note = f"목표원가 대비 {abs(variance)*100:.1f}% 낮음 (사양/공정 누락 확인)"
            else:
                judgment = "🟢 [적합 / 승인]"
                note = f"목표원가 대비 적정 수준 ({variance*100:+.1f}%)"
        else:
            mat_cost = 0
            target_cost = 0
            variance = 0
            judgment = "⚪ [중량/재질 데이터 미흡]"
            note = "견적서 내 부품 중량 또는 재질 식별 불가 (수동 확인 필요)"

        evaluated.append({
            "source_file": file_name,
            "supplier": supplier,
            "part_name": part_name,
            "material": mat,
            "weight_kg": weight,
            "quoted_price": quote,
            "mat_cost": mat_cost,
            "target_cost": target_cost,
            "variance": variance,
            "judgment": judgment,
            "note": note
        })
    return evaluated

# ---------------------------------------------------------
# 4. 엑셀 종합 리포트 생성
# ---------------------------------------------------------
def export_to_excel(results: list, output_filepath: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "견적검토종합결과"
    ws.views.sheetView[0].showGridLines = True

    # 스타일 지정
    font_header = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
    font_data = Font(name="맑은 고딕", size=10)
    font_bold = Font(name="맑은 고딕", size=10, bold=True)
    fill_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    border_thin = Border(
        left=Side(style='thin', color="D9D9D9"), right=Side(style='thin', color="D9D9D9"),
        top=Side(style='thin', color="D9D9D9"), bottom=Side(style='thin', color="D9D9D9")
    )

    headers = [
        "파일명", "협력사", "품목명", "재질", "중량(kg)", 
        "견적단가(원)", "이론재료비", "목표원가(원)", "편차율", "판정결과", "세부검토의견"
    ]
    for col_num, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_num, value=h)
        c.font = font_header
        c.fill = fill_header
        c.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, r in enumerate(results, 2):
        row_vals = [
            r["source_file"], r["supplier"], r["part_name"], r["material"],
            r["weight_kg"], r["quoted_price"], r["mat_cost"], r["target_cost"],
            r["variance"], r["judgment"], r["note"]
        ]
        for col_idx, val in enumerate(row_vals, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = font_data
            cell.border = border_thin
            if col_idx in [1, 2, 3, 4, 10, 11]:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            elif col_idx == 5:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "0.000"
            elif col_idx in [6, 7, 8]:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0"
            elif col_idx == 9:
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "+0.0%;-0.0%;0.0%"
                cell.font = font_bold
            
            if col_idx == 10:
                cell.font = font_bold

    # 열 너비 자동 맞춤
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    wb.save(output_filepath)
    print(f"[+] 엑셀 분석 리포트 저장 완료: {output_filepath}")

# ---------------------------------------------------------
# 메인 실행 루틴
# ---------------------------------------------------------
if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=== [견적 타당성 이미지 자동 검토 시스템] ===")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] GEMINI_API_KEY 환경변수가 설정되지 않았습니다. API 키를 입력해주세요.")
        api_key = input("API Key: ").strip()

    client = genai.Client(api_key=api_key)
    
    # input_quotes 폴더의 이미지 탐색
    extensions = ["*.png", "*.jpg", "*.jpeg", "*.pdf"]
    image_files = []
    for ext in extensions:
        image_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))

    if not image_files:
        print(f"[!] '{INPUT_DIR}' 폴더에 견적서 이미지나 PDF 파일이 없습니다.")
        print(f"    검토할 견적서 파일을 해당 폴더에 넣고 다시 실행해주세요.")
        exit()

    all_evaluated_results = []
    for img_path in image_files:
        fn = os.path.basename(img_path)
        print(f"[*] 처리 중: {fn}...")
        parsed = extract_quote_from_image(client, img_path)
        evaluated = evaluate_items(parsed, fn)
        all_evaluated_results.extend(evaluated)

    out_name = f"견적타당성검토결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    export_to_excel(all_evaluated_results, out_path)
    print("=== 전체 검토 작업 완료 ===")
