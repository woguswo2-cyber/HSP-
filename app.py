import streamlit as st
import io
import time
import os
import pandas as pd
import json
import re
from datetime import datetime
import urllib.request
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
# 2. 서울외환중개(SMBS) 환율 조회 (실패/타임아웃 시 기본값)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_smbs_exchange_rates():
    defaults = {"USD": 1380.0, "CNY": 192.0, "EUR": 1500.0, "INR": 16.5}
    url = "http://www.smbs.biz/ExRate/TodayExRate.jsp"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=2.5).read().decode('euc-kr', 'ignore')
        rates = {}
        for cur in ["USD", "CNY", "EUR", "INR"]:
            m = re.search(cur + r'.*?([0-9,]+\.[0-9]+|[0-9,]+)', html, re.DOTALL)
            if m:
                rates[cur] = float(m.group(1).replace(",", ""))
        for k in defaults:
            if k not in rates or rates[k] == 0:
                rates[k] = defaults[k]
        return rates
    except Exception:
        return defaults

# ---------------------------------------------------------
# 3. 다국어 사전 (KO / EN / ZH)
# ---------------------------------------------------------
I18N = {
    "한국어": {
        "title": "📊 협력사 견적/원가계산서 타당성 자동 분석 및 사정 견적 산출",
        "caption": "공정별 설비효율, 기계경비 배부율, SMBS 환율, 다중 견적서(갑/을지) 교차검증 및 차종/품번 이력 관리를 지원합니다.",
        "settings": "⚙️ 분석 및 사정 기준 설정",
        "api_auto": "🔑 API Key 자동 연동 완료",
        "api_input": "Gemini API Key 입력",
        "ex_header": "💱 통화별 기준 환율 (SMBS)",
        "proj_header": "🚘 부품 / 프로젝트 관리 정보",
        "v_type": "개발 차종 (Project)",
        "p_no": "품번 (Part No.)",
        "p_name": "품명 (Part Name)",
        "proc_sel": "공정 / 업종 선택",
        "eff_lbl": "설비 효율 기준 (권장 Max: {max_eff}%)",
        "labor_job": "중기중앙회 공인 직종: {job_name}",
        "labor_rate": "적용 임율 기준 (원/초)",
        "et_rate": "여유율 / ET율 기준 (%)",
        "markup_hdr": "📑 원가 가산율 통제 기준 (상한선)",
        "mat_mgr": "재료관리비율 상한 (%)",
        "mfg_oh": "간접제조경비율 상한 (노무비 대비 %)",
        "admin_r": "일반관리비율 상한 (%)",
        "profit_r": "영업이익율 상한 (%)",
        "scrap_mode": "스크랩 단가 검증 방식",
        "scrap_p_mode": "실거래가 기준 (원/kg)",
        "scrap_r_mode": "신재 대비 인정율 (%)",
        "scrap_p_in": "당사 실 스크랩 매각 단가 (원/kg)",
        "scrap_r_in": "스크랩 인정 기준율 (%)",
        "tab_audit": "🔍 견적 분석 및 사정",
        "tab_history": "🕒 사정 이력 관리 대시보드",
        "up_hdr": "📂 검토할 원가계산서 입력 (갑지/을지 다중 등록)",
        "paste_tab": "📋 캡처본 연속 붙여넣기 (Ctrl+V)",
        "file_tab": "📁 파일 다중 선택 올리기",
        "paste_b": "📋 현재 캡처본 추가하기",
        "clear_b": "🗑️ 붙여넣은 이미지 초기화",
        "count_msg": "현재 총 {count}장의 이미지가 등록되었습니다.",
        "file_up_lbl": "견적서 파일 선택 (다중 선택 가능)",
        "orig_hdr": "📄 대상 견적서 원본 (총 {count}장)",
        "res_hdr": "🔍 타당성 검토 및 당사 사정 견적",
        "api_warn": "👈 사이드바에 API Key를 입력하거나 Secrets에 등록하세요.",
        "exec_b": "🚀 사정 원가계산서 자동 산출",
        "sub_p": "협력사 제출가",
        "adj_p": "당사 사정 목표가",
        "diff_p": "절감 가능액",
        "diff_r": "절감율",
        "tbl_hdr": "📋 표준 견적 대조 원가계산서 (갑지/을지 종합)",
        "cols": ["구분", "항목", "협력사 제출", "당사 사정가", "차액(절감)", "사정 기준 및 사유"],
        "dl_csv": "📥 사정 원가계산서 엑셀(CSV) 다운로드",
        "hist_hdr": "📊 부품/차종별 누적 원가 사정 및 절감 이력",
        "prompt_lang": "한국어로 상세한 원가 검토 의견 및 협력사 통보용 공식 공문을 작성하세요."
    },
    "English": {
        "title": "📊 Supplier Cost Sheet Audit & Target Price System",
        "caption": "Supports equipment efficiency, overhead allocation, SMBS FX rates, multi-sheet audit, and part history tracking.",
        "settings": "⚙️ Audit Configuration",
        "api_auto": "🔑 API Key Connected",
        "api_input": "Enter Gemini API Key",
        "ex_header": "💱 FX Rates (SMBS Standard)",
        "proj_header": "🚘 Project & Part Info",
        "v_type": "Vehicle Model / Project",
        "p_no": "Part Number (P/N)",
        "p_name": "Part Name",
        "proc_sel": "Select Manufacturing Process",
        "eff_lbl": "Equipment Efficiency Target (Max: {max_eff}%)",
        "labor_job": "Labor Category: {job_name}",
        "labor_rate": "Applied Labor Rate (KRW/sec)",
        "et_rate": "Allowance / ET Rate (%)",
        "markup_hdr": "📑 Cost Mark-up Ceilings",
        "mat_mgr": "Material Management Rate Ceiling (%)",
        "mfg_oh": "Overhead Ceiling (% vs Labor)",
        "admin_r": "SG&A Rate Ceiling (%)",
        "profit_r": "Profit Rate Ceiling (%)",
        "scrap_mode": "Scrap Audit Method",
        "scrap_p_mode": "Market Price (KRW/kg)",
        "scrap_r_mode": "Ratio against Virgin Material (%)",
        "scrap_p_in": "Internal Scrap Sales Unit Price",
        "scrap_r_in": "Scrap Standard Ratio (%)",
        "tab_audit": "🔍 Audit & Target Cost",
        "tab_history": "🕒 Audit History Dashboard",
        "up_hdr": "📂 Upload Cost Sheets (Multi-page Support)",
        "paste_tab": "📋 Clipboard Continuous Paste (Ctrl+V)",
        "file_tab": "📁 Upload Multiple Files",
        "paste_b": "📋 Add Current Clipboard Screenshot",
        "clear_b": "🗑️ Clear Pasted Images",
        "count_msg": "{count} image(s) registered currently.",
        "file_up_lbl": "Select quotation images (multi-select)",
        "orig_hdr": "📄 Source Quotation ({count} pages)",
        "res_hdr": "🔍 Audit Verdict & Target Breakdown",
        "api_warn": "👈 Please enter Gemini API Key or set Secrets.",
        "exec_b": "🚀 Run Target Cost Estimation",
        "sub_p": "Quoted Price",
        "adj_p": "Target Cost",
        "diff_p": "Savings Potential",
        "diff_r": "Savings Ratio",
        "tbl_hdr": "📋 Standard Cost Sheet Audit Comparison",
        "cols": ["Category", "Cost Item", "Submitted", "Target Cost", "Variance", "Audit Remarks"],
        "dl_csv": "📥 Download Target Cost Sheet (CSV)",
        "hist_hdr": "📊 Cumulative Cost Audit & Savings History",
        "prompt_lang": "Provide the complete breakdown rationale and negotiation memo in ENGLISH."
    },
    "中文": {
        "title": "📊 供应商报价/成本核算单审查与目标成本系统",
        "caption": "支持工艺稼动率、机械间接费分摊、首尔外汇中介基准汇率、多页报价交叉验证及履历管理。",
        "settings": "⚙️ 审查基准设置",
        "api_auto": "🔑 API Key 自动绑定成功",
        "api_input": "输入 Gemini API Key",
        "ex_header": "💱 币种基准汇率 (首尔外汇中介/SMBS)",
        "proj_header": "🚘 零件及项目履历信息",
        "v_type": "开发车型 / 项目代码 (Project)",
        "p_no": "零件号 (Part No.)",
        "p_name": "零件名称 (Part Name)",
        "proc_sel": "选择制造工艺 / 行业",
        "eff_lbl": "设备效率上限基准 (建议 Max: {max_eff}%)",
        "labor_job": "官方标准工种: {job_name}",
        "labor_rate": "工时单价基准 (韩元/秒)",
        "et_rate": "宽放率 / ET率基准 (%)",
        "markup_hdr": "📑 费用加成率管控基准 (上限)",
        "mat_mgr": "材料管理费率上限 (%)",
        "mfg_oh": "制造间接费率上限 (对比人工费 %)",
        "admin_r": "一般管理费率上限 (%)",
        "profit_r": "利润率上限 (%)",
        "scrap_mode": "废料单价验证方式",
        "scrap_p_mode": "实际买卖单价基准 (韩元/kg)",
        "scrap_r_mode": "对比新料认可比例 (%)",
        "scrap_p_in": "我司实际废料变卖单价",
        "scrap_r_in": "废料折算基准比例 (%)",
        "tab_audit": "🔍 报价审查与核算",
        "tab_history": "🕒 核价履历管理看板",
        "up_hdr": "📂 录入审查报价单 (支持多页/附件同时比对)",
        "paste_tab": "📋 剪贴板连续截图粘贴 (Ctrl+V)",
        "file_tab": "📁 多文件上传",
        "paste_b": "📋 添加当前截图",
        "clear_b": "🗑️ 清空粘贴图片",
        "count_msg": "当前已登记 {count} 张截图。",
        "file_up_lbl": "选择报价单图片 (支持多选)",
        "orig_hdr": "📄 原始报价单单据 (共 {count} 页)",
        "res_hdr": "🔍 合理性审查及我司目标成本",
        "api_warn": "👈 请在左侧侧边栏配置 Gemini API Key。",
        "exec_b": "🚀 自动核算目标成本核算单",
        "sub_p": "供应商提报单价",
        "adj_p": "我司目标核算单价",
        "diff_p": "预计降本金额",
        "diff_r": "降本比率",
        "tbl_hdr": "📋 标准成本核算对比表 (汇总/明细结合)",
        "cols": ["区分", "项目", "提报金额", "目标核算额", "差额(核减)", "核算基准及理由"],
        "dl_csv": "📥 下载目标核算单 (CSV/Excel)",
        "hist_hdr": "📊 零件/车型累计核价与降本履历",
        "prompt_lang": "请使用简体中文输出审查意见及向供应商发送的官方谈判公文。"
    }
}

# ---------------------------------------------------------
# 4. 공정별 표준 데이터
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "프레스": {"max_eff": 85, "job_name": "판금/프레스조작원", "sec_rate": 4.04, "overhead_rate": 220, "desc": "프레스 설비 상각 및 동력비 장치 공정 (상한 220%)"},
    "가공": {"max_eff": 90, "job_name": "선반/CNC기계조작원", "sec_rate": 4.11, "overhead_rate": 200, "desc": "정밀 공작기계 상각 및 공구비 반영 (상한 200%)"},
    "사출": {"max_eff": 90, "job_name": "플라스틱사출기조작원", "sec_rate": 3.65, "overhead_rate": 200, "desc": "사출기 히터 전력비 및 취출로봇 상각 반영 (상한 200%)"},
    "소결": {"max_eff": 85, "job_name": "소성로/성형기조작원", "sec_rate": 3.71, "overhead_rate": 200, "desc": "분말성형 및 소결로 가스/전력비 반영 (상한 200%)"},
    "다이캐스팅": {"max_eff": 75, "job_name": "다이캐스트원/주조원", "sec_rate": 3.69, "overhead_rate": 250, "desc": "용해로 가스/전력비 및 주조설비 상각 반영 (상한 250%)"},
    "조립": {"max_eff": 90, "job_name": "부품조립원/단순노무원", "sec_rate": 3.66, "overhead_rate": 50, "desc": "작업자 중심 노동집약 공정 (상한 50%)"},
    "일반구매": {"max_eff": 85, "job_name": "제조업 생산직 평균", "sec_rate": 3.98, "overhead_rate": 100, "desc": "범용 외주 임가공/구매 부품 (상한 100%)"},
    "그 외": {"max_eff": 80, "job_name": "제조업 생산직 평균", "sec_rate": 3.98, "overhead_rate": 100, "desc": "기타 가공/조립 (상한 100%)"}
}

# ---------------------------------------------------------
# 5. 사이드바 설정 영역
# ---------------------------------------------------------
with st.sidebar:
    selected_lang = st.selectbox("🌐 Language / 언어 / 语言", ["한국어", "English", "中文"], index=0)
    txt = I18N[selected_lang]

    st.header(txt["settings"])

    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success(txt["api_auto"])
    else:
        api_key = st.text_input(txt["api_input"], type="password", help="구글 AI Studio API 키")

    st.divider()

    # 환율 설정
    st.subheader(txt["ex_header"])
    smbs_rates = fetch_smbs_exchange_rates()
    r_col1, r_col2 = st.columns(2)
    with r_col1:
        rate_usd = st.number_input("USD (달러)", value=float(smbs_rates["USD"]), step=1.0, format="%.2f")
        rate_cny = st.number_input("CNY (위안)", value=float(smbs_rates["CNY"]), step=0.5, format="%.2f")
    with r_col2:
        rate_eur = st.number_input("EUR (유로)", value=float(smbs_rates["EUR"]), step=1.0, format="%.2f")
        rate_inr = st.number_input("INR (루피)", value=float(smbs_rates["INR"]), step=0.1, format="%.2f")
    st.caption("🔗 [서울외환중개(SMBS) 시세 연동](http://www.smbs.biz/ExRate/TodayExRate.jsp)")

    st.divider()

    # 프로젝트 정보
    st.subheader(txt["proj_header"])
    input_vehicle = st.text_input(txt["v_type"], placeholder="예: TB6S / e-Booster / Blower")
    input_part_no = st.text_input(txt["p_no"], placeholder="예: 68000511010 / 16400-XXXXX")
    input_part_name = st.text_input(txt["p_name"], placeholder="예: FLANGE / SHAFT / CORE")

    st.divider()

    # 공정 및 원가 기준
    industry_list = list(INDUSTRY_CONFIG.keys())
    selected_industry = st.selectbox(txt["proc_sel"], industry_list, index=0)
    cfg = INDUSTRY_CONFIG[selected_industry]

    std_eff = st.slider(txt["eff_lbl"].format(max_eff=cfg['max_eff']), 50, 95, cfg["max_eff"], 5)
    st.markdown(f"**{txt['labor_job'].format(job_name=cfg['job_name'])}**")
    std_labor_rate = st.number_input(txt["labor_rate"], 1.0, 15.0, cfg["sec_rate"], 0.1)
    std_et_rate = st.slider(txt["et_rate"], 0, 35, 10, 1)

    st.divider()

    st.subheader(txt["markup_hdr"])
    std_mat_manage_rate = st.slider(txt["mat_mgr"], 0.0, 10.0, 2.0, 0.5)
    std_overhead_rate = st.slider(txt["mfg_oh"], 20, 350, cfg["overhead_rate"], 10)
    st.caption(f"ℹ️ {cfg['desc']}")
    std_admin_rate = st.slider(txt["admin_r"], 1.0, 25.0, 15.0, 0.5)
    std_profit_rate = st.slider(txt["profit_r"], 1.0, 20.0, 10.0, 0.5)

    st.divider()

    scrap_mode = st.radio(txt["scrap_mode"], [txt["scrap_p_mode"], txt["scrap_r_mode"]], index=0)
    if scrap_mode == txt["scrap_p_mode"]:
        target_scrap_price = st.number_input(txt["scrap_p_in"], min_value=0, value=12500, step=500)
        scrap_criteria_text = f"실거래 매각단가: {target_scrap_price:,}원/kg 이상 반영"
    else:
        target_scrap_ratio = st.slider(txt["scrap_r_in"], 50, 90, 65, step=5)
        scrap_criteria_text = f"신재 단가 대비 인정율: {target_scrap_ratio}% 이상 반영"

# ---------------------------------------------------------
# 6. 메인 화면 레이아웃
# ---------------------------------------------------------
st.title(txt["title"])
st.caption(txt["caption"])

main_tab1, main_tab2 = st.tabs([txt["tab_audit"], txt["tab_history"]])

# TAB 1: 분석 및 사정
with main_tab1:
    if "clipboard_images" not in st.session_state:
        st.session_state.clipboard_images = []

    st.write(f"### {txt['up_hdr']}")
    sub_tab1, sub_tab2 = st.tabs([txt["paste_tab"], txt["file_tab"]])

    image_list = []

    with sub_tab1:
        c_btn, c_clr = st.columns([2, 1])
        with c_btn:
            paste_result = paste_image_button(
                label=txt["paste_b"],
                background_color="#1F4E79",
                hover_background_color="#2F5597",
                text_color="#FFFFFF"
            )
        with c_clr:
            if st.button(txt["clear_b"]):
                st.session_state.clipboard_images = []
                st.rerun()

        if paste_result.image_data is not None:
            buf = io.BytesIO()
            paste_result.image_data.save(buf, format="PNG")
            new_bytes = buf.getvalue()
            if not st.session_state.clipboard_images or st.session_state.clipboard_images[-1]["bytes"] != new_bytes:
                st.session_state.clipboard_images.append({"bytes": new_bytes, "mime": "image/png"})

        if st.session_state.clipboard_images:
            image_list = st.session_state.clipboard_images
            st.info(txt["count_msg"].format(count=len(image_list)))

    with sub_tab2:
        uploaded_files = st.file_uploader(txt["file_up_lbl"], type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        if uploaded_files:
            image_list = [{"bytes": f.getvalue(), "mime": f.type} for f in uploaded_files]

    if image_list:
        col1, col2 = st.columns([1, 1], gap="medium")
        with col1:
            st.subheader(txt["orig_hdr"].format(count=len(image_list)))
            for idx, img_item in enumerate(image_list):
                st.image(img_item["bytes"], caption=f"Page {idx + 1}", use_container_width=True)

        with col2:
            st.subheader(txt["res_hdr"])
            if not api_key:
                st.warning(txt["api_warn"])
            else:
                if st.button(txt["exec_b"], type="primary"):
                    with st.spinner("Analyzing quotes and computing target cost..."):
                        client = genai.Client(api_key=api_key)
                        contents = [types.Part.from_bytes(data=x["bytes"], mime_type=x["mime"]) for x in image_list]

                        prompt = f"""
                        당신은 자동차 부품 구매팀 원가 분석관입니다. 제공된 견적서 이미지를 종합 대조하여 사정 원가계산서를 작성하세요.
                        [프로젝트 정보] 차종: '{input_vehicle}', 품번: '{input_part_no}', 품명: '{input_part_name}'
                        [기준 환율] USD:{rate_usd}, CNY:{rate_cny}, EUR:{rate_eur}, INR:{rate_inr} KRW (외화 발생 시 적용)
                        [사정 기준]
                        1. 공정: {selected_industry}, 설비효율: {std_eff}% 이상 필수
                        2. 임율: {std_labor_rate}원/초 (협력사가 더 낮으면 협력사 값 유지)
                        3. 여유율: {std_et_rate}%, 재료관리비: 순재료비의 {std_mat_manage_rate}% 이하 (운반비 중복 배제)
                        4. 간접제조경비율: 상한 {std_overhead_rate}% (협력사 비율이 더 낮으면 협력사치 유지)
                        5. 일반관리비율: Min({std_admin_rate}%, 협력사치), 영업이익율: Min({std_profit_rate}%, 협력사치, 순재료비 이윤 배제)
                        6. 스크랩: {scrap_criteria_text} (복합수지 등 분쇄재 재사용 불가 시 투입량 전체 인정, 금속은 환입 필수)
                        7. 절대 원칙: 총 사정 단가가 협력사 제출 단가를 초과하는 역전 현상 엄격 금지 (사정가 <= 제출가)
                        8. 언어 지침: {txt['prompt_lang']}

                        반드시 유효한 JSON 형식으로만 응답하세요:
                        키 구조:
                        - item_info: vehicle_type, supplier, part_name, part_no
                        - comparison: submitted_price, adjusted_price, cost_reduction, reduction_rate
                        - cost_breakdown: 배열 [category, item, submitted, adjusted, diff, note]
                        - audit_comment: 상세 검토 의견 및 협력사 전달용 공식 공문 문구
                        """
                        contents.append(prompt)

                        for attempt in range(3):
                            try:
                                resp = client.models.generate_content(
                                    model="gemini-3.6-flash",
                                    contents=contents,
                                    config=types.GenerateContentConfig(response_mime_type="application/json")
                                )
                                res_text = resp.text.strip()
                                try:
                                    data = json.loads(res_text, strict=False)
                                except Exception:
                                    c_txt = re.sub(r"^```json\s*", "", res_text)
                                    c_txt = re.sub(r"^```\s*", "", c_txt)
                                    c_txt = re.sub(r"\s*```$", "", c_txt)
                                    data = json.loads(c_txt, strict=False)

                                f_v = input_vehicle or data.get("item_info", {}).get("vehicle_type", "Unknown")
                                f_p = input_part_no or data.get("item_info", {}).get("part_no", "Unknown")
                                f_n = input_part_name or data.get("item_info", {}).get("part_name", "Unknown")
                                f_s = data.get("item_info", {}).get("supplier", "Unknown")
                                comp = data["comparison"]

                                # 이력 누적 저장
                                h_file = "audit_history.csv"
                                new_row = pd.DataFrame({
                                    "일자": [datetime.now().strftime("%Y-%m-%d %H:%M")],
                                    "차종": [f_v], "품번": [f_p], "품명": [f_n], "협력사": [f_s],
                                    "공정": [selected_industry],
                                    "제출가(원)": [round(comp['submitted_price'], 1)],
                                    "사정가(원)": [round(comp['adjusted_price'], 1)],
                                    "절감액(원)": [round(comp['cost_reduction'], 1)],
                                    "절감율(%)": [round(comp['reduction_rate'], 1)]
                                })
                                if os.path.exists(h_file):
                                    new_row.to_csv(h_file, mode='a', header=False, index=False, encoding="utf-8-sig")
                                else:
                                    new_row.to_csv(h_file, mode='w', header=True, index=False, encoding="utf-8-sig")

                                c1, c2, c3, c4 = st.columns(4)
                                c1.metric(txt["sub_p"], f"{comp['submitted_price']:,.1f}")
                                c2.metric(txt["adj_p"], f"{comp['adjusted_price']:,.1f}")
                                c3.metric(txt["diff_p"], f"-{comp['cost_reduction']:,.1f}")
                                c4.metric(txt["diff_r"], f"-{comp['reduction_rate']:.1f}%")

                                st.markdown(f"#### {txt['tbl_hdr']}")
                                df = pd.DataFrame(data["cost_breakdown"])
                                df.columns = txt["cols"]
                                st.dataframe(df, use_container_width=True, hide_index=True)

                                csv_d = df.to_csv(index=False, encoding="utf-8-sig")
                                st.download_button(
                                    label=txt["dl_csv"],
                                    data=csv_d,
                                    file_name="Cost_Audit_Report.csv",
                                    mime="text/csv"
                                )
                                st.divider()

                                if "audit_comment" in data and data["audit_comment"]:
                                    st.markdown(data["audit_comment"])

                                break
                            except Exception as e:
                                if "503" in str(e) and attempt < 2:
                                    time.sleep(3)
                                    continue
                                else:
                                    st.error(f"Error: {e}")
                                    break

# TAB 2: 차종/품번별 사정 이력 관리 대시보드
with main_tab2:
    st.subheader(txt["hist_hdr"])
    h_file = "audit_history.csv"

    if os.path.exists(h_file):
        hist_df = pd.read_csv(h_file, encoding="utf-8-sig")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 검토 건수", f"{len(hist_df)} 건")
        m2.metric("제출 금액 합계", f"{hist_df['제출가(원)'].sum():,.0f} 원")
        m3.metric("사정 목표액 합계", f"{hist_df['사정가(원)'].sum():,.0f} 원")
        m4.metric("총 절감 기여액", f"-{hist_df['절감액(원)'].sum():,.0f} 원")

        st.divider()

        f1, f2 = st.columns(2)
        with f1:
            s_v = st.text_input("차종으로 검색", "")
        with f2:
            s_p = st.text_input("품번/품명으로 검색", "")

        f_df = hist_df
        if s_v:
            f_df = f_df[f_df["차종"].str.contains(s_v, na=False, case
