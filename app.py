import streamlit as st
import io
import time
import os
import pandas as pd
import json
import re
from datetime import datetime
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="구매 견적/원가계산서 타당성 자동 검토",
    page_icon="📊",
    layout="wide"
)

# ---------------------------------------------------------
# 2. 다국어 텍스트 사전 (KO / EN / ZH)
# ---------------------------------------------------------
I18N = {
    "한국어": {
        "title": "📊 협력사 견적/원가계산서 타당성 자동 분석 및 사정 견적 산출",
        "caption": "공정별 설비효율, 기계경비 배부율, 다중 견적서(갑/을지) 교차검증 및 차종/품번 이력 관리를 지원합니다.",
        "settings": "⚙️ 분석 및 사정 기준 설정",
        "api_auto": "🔑 API Key 자동 연동 완료",
        "api_input": "Gemini API Key 입력",
        "project_info": "🚘 부품 / 프로젝트 관리 정보",
        "vehicle_type": "개발 차종 (Project)",
        "part_no": "품번 (Part No.)",
        "part_name": "품명 (Part Name)",
        "proc_select": "공정 / 업종 선택",
        "eff_label": "설비 효율 기준 (권장 Max: {max_eff}%)",
        "labor_job": "중기중앙회 공인 직종: {job_name}",
        "labor_rate": "적용 임율 기준 (원/초)",
        "et_rate": "여유율 / ET율 기준 (%)",
        "cost_limits": "📑 원가 가산율 통제 기준 (상한선)",
        "mat_manage": "재료관리비율 상한 (%)",
        "overhead": "간접제조경비율 상한 (노무비 대비 %)",
        "admin_rate": "일반관리비율 상한 (%)",
        "profit_rate": "영업이익율 상한 (%)",
        "scrap_mode": "스크랩 단가 검증 방식",
        "scrap_price_mode": "실거래가 기준 (원/kg)",
        "scrap_ratio_mode": "신재 대비 인정율 (%)",
        "scrap_price_input": "당사 실 스크랩 매각 단가 (원/kg)",
        "scrap_ratio_input": "스크랩 인정 기준율 (%)",
        "tab_audit": "🔍 견적 분석 및 사정",
        "tab_history": "🕒 사정 이력 관리 대시보드",
        "upload_header": "📂 검토할 원가계산서 입력 (갑지, 을지 등 여러 장 업로드 가능)",
        "tab_paste": "📋 캡처본 연속 붙여넣기 (Ctrl+V)",
        "tab_file": "📁 파일 여러 장 선택 올리기",
        "paste_btn": "📋 현재 캡처본 추가하기",
        "clear_btn": "🗑️ 붙여넣은 이미지 초기화",
        "count_info": "현재 총 {count}장의 캡처 이미지가 등록되었습니다.",
        "file_uploader": "견적서 파일 선택 (갑지, 을지 등 다중 선택)",
        "orig_header": "📄 대상 견적서 원본 (총 {count}장)",
        "result_header": "🔍 타당성 검토 및 당사 사정 견적",
        "api_warning": "👈 왼쪽 사이드바에 Gemini API Key를 입력하거나 Secrets에 등록해주세요.",
        "exec_btn": "🚀 사정 원가계산서 자동 산출",
        "sub_price": "협력사 제출가",
        "adj_price": "당사 사정 목표가",
        "diff_price": "절감 가능액",
        "diff_rate": "절감율",
        "table_header": "📋 표준 견적 대조 원가계산서 (갑지/을지 종합)",
        "col_cat": "구분",
        "col_item": "항목",
        "col_sub": "협력사 제출",
        "col_adj": "당사 사정가",
        "col_diff": "차액(절감)",
        "col_note": "사정 기준 및 사유",
        "dl_csv": "📥 사정 원가계산서 엑셀(CSV) 다운로드",
        "prompt_lang": "한국어로 상세하고 전문적인 원가 검토 의견 및 협력사 발송용 공문을 작성하세요."
    },
    "English": {
        "title": "📊 Supplier Cost Sheet Audit & Target Price Estimation System",
        "caption": "Supports industry equipment efficiency, overhead allocation, multi-page sheet audit, and part history tracking.",
        "settings": "⚙️ Audit & Target Cost Configuration",
        "api_auto": "🔑 API Key Automatically Connected",
        "api_input": "Enter Gemini API Key",
        "project_info": "🚘 Project & Part Management Info",
        "vehicle_type": "Vehicle Model / Project",
        "part_no": "Part Number (P/N)",
        "part_name": "Part Name",
        "proc_select": "Select Manufacturing Process",
        "eff_label": "Equipment Efficiency Target (Max: {max_eff}%)",
        "labor_job": "Standard Labor Category: {job_name}",
        "labor_rate": "Applied Labor Rate (KRW/sec)",
        "et_rate": "Allowance / ET Rate (%)",
        "cost_limits": "📑 Cost Mark-up Ceilings",
        "mat_manage": "Material Management Rate Ceiling (%)",
        "overhead": "Manufacturing Overhead Ceiling (% vs Labor)",
        "admin_rate": "SG&A Rate Ceiling (%)",
        "profit_rate": "Operating Profit Rate Ceiling (%)",
        "scrap_mode": "Scrap Audit Method",
        "scrap_price_mode": "Actual Market Price (KRW/kg)",
        "scrap_ratio_mode": "Ratio against Virgin Material (%)",
        "scrap_price_input": "Internal Actual Scrap Sales Unit Price",
        "scrap_ratio_input": "Scrap Credit Standard Ratio (%)",
        "tab_audit": "🔍 Quotation Audit & Calculation",
        "tab_history": "🕒 Cost Audit History Dashboard",
        "upload_header": "📂 Upload Cost Sheets (Supports Multi-page Quotes)",
        "tab_paste": "📋 Continuous Clipboard Paste (Ctrl+V)",
        "tab_file": "📁 Upload Multiple Files",
        "paste_btn": "📋 Add Current Clipboard Screenshot",
        "clear_btn": "🗑️ Clear Pasted Images",
        "count_info": "{count} screenshot(s) registered currently.",
        "file_uploader": "Select quotation images (multi-select supported)",
        "orig_header": "📄 Source Quotation ({count} pages)",
        "result_header": "🔍 Audit Verdict & Target Breakdown",
        "api_warning": "👈 Please enter Gemini API Key in sidebar or register it in Secrets.",
        "exec_btn": "🚀 Run Target Cost Estimation",
        "sub_price": "Quoted Price",
        "adj_price": "Target Cost",
        "diff_price": "Savings Potential",
        "diff_rate": "Savings Ratio",
        "table_header": "📋 Standard Cost Sheet Audit Comparison",
        "col_cat": "Category",
        "col_item": "Cost Item",
        "col_sub": "Submitted",
        "col_adj": "Target Cost",
        "col_diff": "Variance (Savings)",
        "col_note": "Audit Basis & Remarks",
        "dl_csv": "📥 Download Target Cost Sheet (CSV)",
        "prompt_lang": "Provide the complete analysis, breakdown rationale, and official negotiation memo in ENGLISH."
    },
    "中文": {
        "title": "📊 供应商报价/成本核算单自动审查与目标成本核算系统",
        "caption": "支持工艺设备稼动率、机械间接费分摊、多页报价单交叉验证及车型/零件履历管理。",
        "settings": "⚙️ 审查及目标成本核算基准设置",
        "api_auto": "🔑 API Key 自动绑定成功",
        "api_input": "输入 Gemini API Key",
        "project_info": "🚘 零件及项目履历管理信息",
        "vehicle_type": "开发车型 / 项目代码 (Project)",
        "part_no": "零件号 (Part No.)",
        "part_name": "零件名称 (Part Name)",
        "proc_select": "选择制造工艺 / 行业",
        "eff_label": "设备效率上限基准 (建议 Max: {max_eff}%)",
        "labor_job": "官方标准工种: {job_name}",
        "labor_rate": "工时单价基准 (韩元/秒)",
        "et_rate": "宽放率 / ET率基准 (%)",
        "cost_limits": "📑 费用加成率管控基准 (上限)",
        "mat_manage": "材料管理费率上限 (%)",
        "overhead": "制造间接费率上限 (对比人工费 %)",
        "admin_rate": "一般管理费率上限 (%)",
        "profit_rate": "利润率上限 (%)",
        "scrap_mode": "废料单价验证方式",
        "scrap_price_mode": "实际买卖单价基准 (韩元/kg)",
        "scrap_ratio_mode": "对比新料认可比例 (%)",
        "scrap_price_input": "我司实际废料变卖单价",
        "scrap_ratio_input": "废料折算基准比例 (%)",
        "tab_audit": "🔍 报价审查与核算",
        "tab_history": "🕒 核价履历管理看板",
        "upload_header": "📂 录入审查报价单 (支持多页/附件同时比对)",
        "tab_paste": "📋 剪贴板连续截图粘贴 (Ctrl+V)",
        "tab_file": "📁 多文件上传",
        "paste_btn": "📋 添加当前截图",
        "clear_btn": "🗑️ 清空粘贴图片",
        "count_info": "当前已登记 {count} 张截图。",
        "file_uploader": "选择报价单图片 (支持多选)",
        "orig_header": "📄 原始报价单单据 (共 {count} 页)",
        "result_header": "🔍 合理性审查及我司目标成本",
        "api_warning": "👈 请在左侧侧边栏输入 Gemini API Key 或在 Secrets 中配置。",
        "exec_btn": "🚀 自动核算目标成本核算单",
        "sub_price": "供应商提报单价",
        "adj_price": "我司目标核算单价",
        "diff_price": "预计降本金额",
        "diff_rate": "降本比率",
        "table_header": "📋 标准成本核算对比表 (汇总/明细结合)",
        "col_cat": "区分",
        "col_item": "项目",
        "col_sub": "提报金额",
        "col_adj": "目标核算额",
        "col_diff": "差额(核减)",
        "col_note": "核算基准及核减理由",
        "dl_csv": "📥 下载目标核算单 (CSV/Excel)",
        "prompt_lang": "请使用简体中文输出详细的审查意见、剔除理由及向供应商发送的官方谈判公文。"
    }
}

# ---------------------------------------------------------
# 3. 공정별 표준 데이터 맵
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "프레스": {
        "max_eff": 85,
        "job_name": "판금/프레스조작원",
        "sec_rate": 4.04,
        "overhead_rate": 220,
        "desc": "고가 프레스 설비 상각 및 동력비가 큰 장치 공정 (상한 220%)"
    },
    "가공": {
        "max_eff": 90,
        "job_name": "선반/CNC기계조작원",
        "sec_rate": 4.11,
        "overhead_rate": 200,
        "desc": "정밀 공작기계 상각 및 절삭유/공구비 반영 (상한 200%)"
    },
    "사출": {
        "max_eff": 90,
        "job_name": "플라스틱사출기조작원",
        "sec_rate": 3.65,
        "overhead_rate": 200,
        "desc": "사출 성형기 히터 전력비 및 취출 로봇 상각비 반영 (상한 200%)"
    },
    "소결": {
        "max_eff": 85,
        "job_name": "소성로/성형기조작원",
        "sec_rate": 3.71,
        "overhead_rate": 200,
        "desc": "분말성형 프레스 및 연속 소결로 분위기가스/전력비 반영 (상한 200%)"
    },
    "다이캐스팅": {
        "max_eff": 75,
        "job_name": "다이캐스트원/주조원",
        "sec_rate": 3.69,
        "overhead_rate": 250,
        "desc": "용해로 가스·전력비 및 고온 주조 설비 감가상각 반영 (상한 250%)"
    },
    "조립": {
        "max_eff": 90,
        "job_name": "부품조립원/단순노무원",
        "sec_rate": 3.66,
        "overhead_rate": 50,
        "desc": "작업자 중심 노동집약 공정, 치구/소모품 위주 (상한 50%)"
    },
    "일반구매": {
        "max_eff": 85,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98,
        "overhead_rate": 100,
        "desc": "범용 외주 임가공/구매 부품 표준선 (상한 100%)"
    },
    "그 외": {
        "max_eff": 80,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98,
        "overhead_rate": 100,
        "desc": "기타 가공/조립 표준선 (상한 100%)"
    }
}

# ---------------------------------------------------------
# 4. 사이드바 설정 (언어 선택 & 프로젝트 이력 정보 & 원가 기준)
# ---------------------------------------------------------
with st.sidebar:
    # [A] 언어 선택창
    selected_lang = st.selectbox("🌐 Language / 언어 / 语言", ["한국어", "English", "中文"], index=0)
    txt = I18N[selected_lang]

    st.header(txt["settings"])

    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success(txt["api_auto"])
    else:
        api_key = st.text_input(txt["api_input"], type="password", help="구글 AI Studio API 키")

    st.divider()

    # [B] 개발 차종 및 품번 이력 관리 입력란
    st.subheader(txt["project_info"])
    input_vehicle = st.text_input(txt["vehicle_type"], placeholder="예: TB6S / e-Booster / Blower")
    input_part_no = st.text_input(txt["part_no"], placeholder="예: 68000511010 / 16400-XXXXX")
    input_part_name = st.text_input(txt["part_name"], placeholder="예: FLANGE / SHAFT / CORE")

    st.divider()

    # [C] 공정 선택
    industry_list = list(INDUSTRY_CONFIG.keys())
    selected_industry = st.selectbox(txt["proc_select"], industry_list, index=0)
    cfg = INDUSTRY_CONFIG[selected_industry]

    std_eff = st.slider(
        txt["eff_label"].format(max_eff=cfg['max_eff']),
        min_value=50,
        max_value=95,
        value=cfg["max_eff"],
        step=5
    )

    st.markdown(f"**{txt['labor_job'].format(job_name=cfg['job_name'])}**")
    std_labor_rate = st.number_input(
        txt["labor_rate"],
        min_value=1.0,
        max_value=15.0,
        value=cfg["sec_rate"],
        step=0.1
    )

    std_et_rate = st.slider(
        txt["et_rate"],
        min_value=0,
        max_value=35,
        value=10,
        step=1
    )

    st.divider()

    # [D] 원가 가산율 통제 기준
    st.subheader(txt["cost_limits"])
    std_mat_manage_rate = st.slider(txt["mat_manage"], 0.0, 10.0, 2.0, 0.5)
    std_overhead_rate = st.slider(txt["overhead"], 20, 350, cfg["overhead_rate"], 10)
    st.caption(f"ℹ️ {cfg['desc']}")
    std_admin_rate = st.slider(txt["admin_rate"], 1.0, 25.0, 15.0, 0.5)
    std_profit_rate = st.slider(txt["profit_rate"], 1.0, 20.0, 10.0, 0.5)

    st.divider()

    # [E] 스크랩 검증 방식
    scrap_mode = st.radio(txt["scrap_mode"], [txt["scrap_price_mode"], txt["scrap_ratio_mode"]], index=0)
    if scrap_mode == txt["scrap_price_mode"]:
        target_scrap_price = st.number_input(txt["scrap_price_input"], min_value=0, value=12500, step=500)
        scrap_criteria_text = f"실거래 매각단가: {target_scrap_price:,}원/kg 이상 반영 (재활용/매각 가능 소재에 한함)"
    else:
        target_scrap_ratio = st.slider(txt["scrap_ratio_input"], 50, 90, 65, step=5)
        scrap_criteria_text = f"신재 단가 대비 인정 기준율: {target_scrap_ratio}% 이상 반영 (재활용/매각 가능 소재에 한함)"

# ---------------------------------------------------------
# 5. 메인 레이아웃 (탭: 분석 vs 이력 관리)
# ---------------------------------------------------------
st.title(txt["title"])
st.caption(txt["caption"])

main_tab1, main_tab2 = st.tabs([txt["tab_audit"], txt["tab_history"]])

# ---------------------------------------------------------
# TAB 1: 견적 분석 및 사정
# ---------------------------------------------------------
with main_tab1:
    if "clipboard_images" not in st.session_state:
        st.session_state.clipboard_images = []

    st.write(f"### {txt['upload_header']}")
    sub_tab1, sub_tab2 = st.tabs([txt["tab_paste"], txt["tab_file"]])

    image_list = []

    with sub_tab1:
        col_btn, col_clear = st.columns([2, 1])
        with col_btn:
            paste_result = paste_image_button(
                label=txt["paste_btn"],
                background_color="#1F4E79",
                hover_background_color="#2F5597",
                text_color="#FFFFFF"
            )
        with col_clear:
            if st.button(txt["clear_btn"]):
                st.session_state.clipboard_images = []
                st.rerun()

        if paste_result.image_data is not None:
            buf = io.BytesIO()
            paste_result.image_data.save(buf, format="PNG")
            new_bytes = buf.getvalue()
            if not st.session_state.clipboard_images or st.session_state.clipboard_images[-1]["bytes"] != new_bytes:
                st.session_state.clipboard_images.append({
                    "bytes": new_bytes,
                    "mime": "image/png"
                })

        if st.session_state.clipboard_images:
            image_list = st.session_state.clipboard_images
            st.info(txt["count_info"].format(count=len(image_list)))

    with sub_tab2:
        uploaded_files = st.file_uploader(
            txt["file_uploader"],
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        if uploaded_files:
            image_list = [{"bytes": f.getvalue(), "mime": f.type} for f in uploaded_files]

    # 분석 실행부
    if image_list:
        col1, col2 = st.columns([1, 1], gap="medium")

        with col1:
            st.subheader(txt["orig_header"].format(count=len(image_list)))
            for idx, img_item in enumerate(image_list):
                st.image(img_item["bytes"], caption=f"Page {idx + 1}", use_container_width=True)

        with col2:
            st.subheader(txt["result_header"])
            if not api_key:
                st.warning(txt["api_warning"])
            else:
                if st.button(txt["exec_btn"], type="primary"):
                    spin_msg = "Analyzing quotations, cross-referencing sheets & auditing target cost..."
                    with st.spinner(spin_msg):
                        client = genai.Client(api_key=api_key)

                        contents = []
                        for img_item in image_list:
                            contents.append(types.Part.from_bytes(data=img_item["bytes"], mime_type=img_item["mime"]))

                        prompt = f"""
                        당신은 자동차 부품 및 정밀제조업 구매팀의 원가 분석 수석관입니다.
                        제공된 복수의 원가계산서 이미지(갑지-총괄 요약표, 을지-공정/재료 세부명세 등)를 종합 대조하여 과다 계상분을 삭감하고 '정상 사정 원가계산서'를 재계산하세요.

                        [프로젝트 및 부품 정보]
                        - 입력된 차종: '{input_vehicle}' (비어있다면 견적서에서 자동 추출)
                        - 입력된 품번: '{input_part_no}' (비어있다면 견적서에서 자동 추출)
                        - 입력된 품명: '{input_part_name}' (비어있다면 견적서에서 자동 추출)

                        [갑지/을지 교차 분석 핵심 지침]
                        1. 을지(세부내역)의 투입단중, C/T, 임율, 기계경비, 스크랩 환입을 정밀 검증하여 적정 제조원가를 도출하세요.
                        2. 을지의 합계 금액과 갑지(총괄표)의 재료비, 가공비, 일반관리비, 이윤이 일치하는지 대조하고 중복 계상(운반비, 관리비 등)을 적발하세요.

                        [당사 사정 원가 통제 기준]
                        1. 적용 공정: {selected_industry} (특성: {cfg['desc']})
                        2. 기준 설비 효율: {std_eff}% 이상 필수 (원가서 기재 효율 미달 시 삭감)
                        3. 적용 임율 기준: {std_labor_rate} 원/초 (중기중앙회 공인 노임단가 초과분 삭감, 단 협력사가 더 낮은 임율을 적었다면 협력사 값 유지)
                        4. 여유율(ET율): 기준 {std_et_rate}% (초과 반영된 준비시간 배제)
                        5. 재료관리비율: 순재료비의 {std_mat_manage_rate}% 이하 (입고운반비/보관비 중복 반영 엄격 배제)
                        6. 간접제조경비율: 당사 상한 기준은 {std_overhead_rate}%이나, 협력사 제출 비율이 더 낮다면 협력사 제출치 유지.
                        7. 일반관리비율: 당사 상한 기준 {std_admin_rate}%와 협력사 제출 비율 중 낮은 비율(Min) 적용.
                        8. 영업이익율: 당사 상한 기준 {std_profit_rate}%와 협력사 제출 비율 중 낮은 비율(Min) 적용 (순재료비 이윤 배제).
                        9. 스크랩 검증: {scrap_criteria_text}
                           - 복합수지(PP TD20%, PA66 GF30% 등)로 분쇄재 재사용이 불가한 사출품은 투입량 전체를 재료비로 인정하고 스크랩 환입은 0원 처리.
                           - 금속 프레스/가공/다이캐스팅은 스크랩 매각 환입 필수 반영.

                        [절대 원칙 - 단가 역전 금지]
                        - 협력사가 당사 기준보다 낮게 책정한 항목을 강제로 올려 총 사정가가 협력사 제출가보다 커지는 역전 현상을 절대 발생시키지 마십시오.

                        [언어 출력 원칙]
                        - {txt['prompt_lang']}

                        [출력 형식 가이드]
                        반드시 유효한 JSON 형식으로만 응답하세요. audit_comment 내부 줄바꿈은 반드시 이스케이프(\\\\n) 처리하세요.
                        키 구조:
                        - item_info: vehicle_type, supplier, part_name, part_no
                        - comparison: submitted_price, adjusted_price, cost_reduction, reduction_rate
                        - cost_breakdown: 배열 형태, 각 요소는 category, item, submitted, adjusted, diff, note
                          (항목: 투입재료비, 스크랩환입(-), 순재료비, 재료관리비, 직접노무비, 간접제조경비, 제조원가 합계, 일반관리비, 영업이익, 최종 견적 단가)
                        - audit_comment: 상세 검토 의견, 삭감 사유, 협력사 전달용 공식 공문 문구
                        """
                        contents.append(prompt)

                        for attempt in range(3):
                            try:
                                response = client.models.generate_content(
                                    model="gemini-3.6-flash",
                                    contents=contents,
                                    config=types.GenerateContentConfig(
                                        response_mime_type="application/json"
                                    )
                                )
                                res_text = response.text.strip()

                                try:
                                    data = json.loads(res_text, strict=False)
                                except Exception:
                                    clean_text = re.sub(r"^```json\s*", "", res_text)
                                    clean_text = re.sub(r"^```\s*", "", clean_text)
                                    clean_text = re.sub(r"\s*```$", "", clean_text)
                                    data = json.loads(clean_text, strict=False)

                                # 이력 저장을 위한 품목 정보 보정
                                final_vehicle = input_vehicle or data.get("item_info", {}).get("vehicle_type", "Unknown")
                                final_part_no = input_part_no or data.get("item_info", {}).get("part_no", "Unknown")
                                final_part_name = input_part_name or data.get("item_info", {}).get("part_name", "Unknown")
                                final_supplier = data.get("item_info", {}).get("supplier", "Unknown")

                                comp = data["comparison"]

                                # CSV 파일에 이력 자동 누적 저장
                                history_file = "audit_history.csv"
                                new_history = {
                                    "일자": [datetime.now().strftime("%Y-%m-%d %H:%M")],
                                    "차종": [final_vehicle],
                                    "품번": [final_part_no],
                                    "품명": [final_part_name],
                                    "협력사": [final_supplier],
                                    "공정": [selected_industry],
                                    "제출가(원)": [round(comp['submitted_price'], 1)],
                                    "사정가(원)": [round(comp['adjusted_price'], 1)],
                                    "절감액(원)": [round(comp['cost_reduction'], 1)],
                                    "절감율(%)": [round(comp['reduction_rate'], 1)]
                                }
                                new_hist_df = pd.DataFrame(new_history)
                                if os.path.exists(history_file):
                                    new_hist_df.to_csv(history_file, mode='a', header=False, index=False, encoding="utf-8-sig")
                                else:
                                    new_hist_df.to_csv(history_file, mode='w', header=True, index=False, encoding="utf-8-sig")

                                # 상단 지표 카드 출력
                                c_sub, c_adj, c_diff, c_rate = st.columns(4)
                                c_sub.metric(txt["sub_price"], f"{comp['submitted_price']:,.1f}")
                                c_adj.metric(txt["adj_price"], f"{comp['adjusted_price']:,.1f}")
                                c_diff.metric(txt["diff_price"], f"-{comp['cost_reduction']:,.1f}")
                                c_rate.metric(txt["diff_rate"], f"-{comp['reduction_rate']:.1f}%")

                                # 표준 원가계산서 대조 테이블
                                st.markdown(f"#### {txt['table_header']}")
                                df = pd.DataFrame(data["cost_breakdown"])
                                df.columns = [txt["col_cat"], txt["col_item"], txt["col_sub"], txt["col_adj"], txt["col_diff"], txt["col_note"]]
                                st.dataframe(df, use_container_width=True, hide_index=True)

                                # CSV 다운로드
                                csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                                st.download_button(
                                    label=txt["dl_csv"],
                                    data=csv_data,
                                    file_name=f"Audit_Report_{final_part_no}.csv",
                                    mime="text/csv"
                                )
                                st.divider()

                                # 상세 검토 의견 및 공문 텍스트
                                if "audit_comment" in data and data["audit_comment"]:
                                    st.markdown(data["audit_comment"])

                                break
                            except Exception as e:
                                if "503" in str(e) and attempt < 2:
                                    time.sleep(3)
                                    continue
                                else:
                                    st.error(f"Error during analysis: {e}")
                                    break

# ---------------------------------------------------------
# TAB 2: 차종/품번별 사정 이력 관리 대시보드
# ---------------------------------------------------------
with main_tab2:
    st.subheader("📊 부품/차종별 누적 원가 사정 및 절감 이력")
    history_file = "audit_history.csv"

    if os.path.exists(history_file):
        hist_df = pd.read_csv(history_file, encoding="utf-8-sig")
        
        # 상단 누적 통계 카드
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 검토 건수", f"{len(hist_df)} 건")
        m2.metric("총 제출 금액 합계", f"{hist_df['제출가(원)'].sum():,.0f} 원")
        m3.metric("총 사정 목표액 합계", f"{hist_df['사정가(원)'].sum():,.0f} 원")
        total_saving = hist_df['절감액(원)'].sum()
        m4.metric("총 절감 기여액", f"-{total_saving:,.0f} 원")

        st.divider()

        # 검색 필터
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            search_vehicle = st.text_input("차종으로 검색", "")
        with f_col2:
            search_part = st.text_input("품번/품명으로 검색", "")

        filtered_df = hist_df
        if search_vehicle:
            filtered_df = filtered_df[filtered_df["차종"].str.contains(search_vehicle, na=False, case=False)]
        if search_part:
            filtered_df = filtered_df[
                filtered_df["품번"].str.contains(search_part, na=False, case=False) |
                filtered_df["품명"].str.contains(search_part, na=False, case=False)
            ]

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

        # 전체 이력 다운로드 버튼
        full_csv = hist_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 누적 이력 전체 엑셀(CSV) 다운로드",
            data=full_csv,
            file_name="All_Cost_Audit_History.csv",
            mime="text/csv"
        )
    else:
        st.info("아직 저장된 사정 이력이 없습니다. 견적서를 분석하면 이곳에 차종/품번별 절감 실적이 자동으로 누적 기록됩니다.")
