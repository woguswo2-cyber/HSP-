import streamlit as st
import io, time, os, re, json, urllib.request
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

# 1. 페이지 설정
st.set_page_config(page_title="Cost Sheet Audit & Benchmark System", page_icon="📊", layout="wide")

# 소수점 동적 포맷 헬퍼 (견적서 원본 자릿수 보존)
def fmt_price(val, prec=0):
    try:
        fval = float(val)
        if prec == 0:
            return f"{fval:,.0f}"
        return f"{fval:,.{prec}f}"
    except Exception:
        return str(val)

# 2. 다국어 텍스트 사전 및 공정 매핑
I18N = {
    "한국어": {
        "title": "📊 협력사 견적/원가계산서 타당성 자동 분석 및 체리피킹 비교 시스템",
        "caption": "설비효율, 기계경비 배부율, SMBS 환율, 목표가 역산 및 2개사 견적 1:1 비교(체리피킹)를 지원합니다.",
        "settings": "⚙️ 분석 기준 설정",
        "api_auto": "🔑 API Key 자동 연동 완료",
        "api_input": "Gemini API Key 입력",
        "fx_header": "💱 기준 통화 및 환율",
        "cur_select": "적용 통화 선택",
        "cur_rate_label": "1 {cur} 당 원화 환율 (원)",
        "krw_info": "원화(KRW) 기준 견적 (환율 1.0 적용)",
        "smbs_link": "🔗 서울외환중개(SMBS) 일별 시세 연동",
        "proj_header": "🚘 부품 / 프로젝트 정보",
        "v_type": "차종 (Project)",
        "p_no": "품번 (Part No.)",
        "p_name": "품명 (Part Name)",
        "target_p_label": "🎯 목표 타겟 단가 (Target Price, 선택)",
        "target_p_help": "입력 시 목표가를 맞추기 위해 어느 원가 항목에서 얼마를 깎아야 하는지 자동 역산 배분합니다. (0 입력 시 표준 사정)",
        "proc_sel": "공정 선택",
        "eff_lbl": "설비 효율 기준 (권장 Max: {eff}%)",
        "labor_job": "공인 직종: {job}",
        "labor_rate": "적용 임율 기준 (원/초)",
        "et_rate": "여유율 / ET율 기준 (%)",
        "markup_hdr": "📑 원가 가산율 통제 기준 (상한선)",
        "mat_mgr": "재료관리비율 상한 (%)",
        "mfg_oh": "간접제조경비율 상한 (노무비 대비 %)",
        "admin_r": "일반관리비율 상한 (%)",
        "profit_r": "영업이익율 상한 (%)",
        "scrap_lbl": "실 스크랩 매각가 (원/kg)",
        "tab_audit": "🔍 단일 견적 분석 & 목표가 산출",
        "tab_compare": "⚔️ 2개사 견적 비교 & 체리피킹",
        "tab_history": "🕒 사정 이력 대시보드",
        "up_hdr": "📂 견적서 등록 (갑지/을지 다중 등록 가능)",
        "paste_tab": "📋 클립보드 붙여넣기",
        "file_tab": "📁 파일 업로드",
        "paste_b": "📋 캡처 추가하기",
        "clear_b": "🗑️ 붙여넣기 초기화",
        "count_msg": "등록된 캡처본: {count}장",
        "file_up_lbl": "이미지 파일 선택 (다중 선택 가능)",
        "orig_hdr": "📄 대상 견적서 ({count}장)",
        "res_hdr": "🔍 분석 및 사정 견적 (타겟 역산)",
        "api_warn": "👈 사이드바에 API Key를 설정해주세요.",
        "exec_b": "🚀 사정 원가계산서 산출",
        "exec_compare_b": "⚔️ 2개사 견적 대조 및 체리피킹 분석 실행",
        "sub_p": "협력사 제출가",
        "adj_p": "당사 사정(목표)가",
        "diff_p": "절감 가능액",
        "diff_r": "절감율",
        "tbl_hdr": "📋 표준 견적 대조표 (목표가 역산 배분)",
        "cols": ["구분", "항목", "제출가", "사정(목표)가", "차액(절감)", "사정 기준 및 네고 타격 포인트"],
        "dl_csv": "📥 사정 원가계산서 CSV 다운로드",
        "hist_hdr": "📊 부품/차종별 누적 원가 사정 이력",
        "hist_search_v": "차종 검색",
        "hist_search_p": "품번/품명 검색",
        "hist_search_s": "협력사(업체명) 검색",
        "hist_dl_csv": "📥 전체 이력 CSV 다운로드",
        "hist_empty": "저장된 사정 이력이 없습니다. 견적서 분석을 실행하면 자동으로 누적 기록됩니다.",
        "prompt_lang": "한국어로 상세하고 전문적인 원가 검토 의견 및 협력사 공식 네고 공문 문구를 작성하세요.",
        "proc_options": {
            "프레스": "프레스",
            "가공": "가공",
            "사출": "사출",
            "소결": "소결",
            "다이캐스팅": "다이캐스팅",
            "조립": "조립",
            "일반구매": "일반구매",
            "그 외": "그 외"
        }
    },
    "English": {
        "title": "📊 Supplier Cost Sheet Audit & Cherry-Picking Benchmark System",
        "caption": "Supports equipment efficiency, overhead allocation, SMBS FX rates, Target Price reverse engineering, and 1:1 cross-supplier benchmark.",
        "settings": "⚙️ Audit Configuration",
        "api_auto": "🔑 API Key Automatically Connected",
        "api_input": "Enter Gemini API Key",
        "fx_header": "💱 Currency & Exchange Rate",
        "cur_select": "Select Applied Currency",
        "cur_rate_label": "Exchange Rate for 1 {cur} (in KRW)",
        "krw_info": "KRW-based Quotation (Rate 1.0 Applied)",
        "smbs_link": "🔗 SMBS Foreign Exchange Daily Rate",
        "proj_header": "🚘 Project & Part Information",
        "v_type": "Vehicle Model / Project",
        "p_no": "Part Number (P/N)",
        "p_name": "Part Name",
        "target_p_label": "🎯 Target Price (Optional)",
        "target_p_help": "If specified, reverse-engineers cost items to reach target price. (0 = Standard Audit)",
        "proc_sel": "Manufacturing Process",
        "eff_lbl": "Equipment Efficiency Target (Max: {eff}%)",
        "labor_job": "Labor Category: {job}",
        "labor_rate": "Applied Labor Rate (KRW/sec)",
        "et_rate": "Allowance / ET Rate (%)",
        "markup_hdr": "📑 Cost Mark-up Ceilings",
        "mat_mgr": "Material Management Rate Ceiling (%)",
        "mfg_oh": "Overhead Ceiling (% vs Labor)",
        "admin_r": "SG&A Rate Ceiling (%)",
        "profit_r": "Profit Rate Ceiling (%)",
        "scrap_lbl": "Actual Scrap Sales Unit Price (KRW/kg)",
        "tab_audit": "🔍 Single Quote Audit & Target Cost",
        "tab_compare": "⚔️ 2-Supplier Cross Audit & Cherry-Picking",
        "tab_history": "🕒 Audit History Dashboard",
        "up_hdr": "📂 Upload Quotation Sheets (Multi-sheet Support)",
        "paste_tab": "📋 Clipboard Paste",
        "file_tab": "📁 File Upload",
        "paste_b": "📋 Add Screenshot",
        "clear_b": "🗑️ Clear Pasted Images",
        "count_msg": "Registered Screenshots: {count}",
        "file_up_lbl": "Select quotation images (multi-select)",
        "orig_hdr": "📄 Source Quotation ({count} pages)",
        "res_hdr": "🔍 Audit Verdict & Target Breakdown",
        "api_warn": "👈 Please configure Gemini API Key in sidebar.",
        "exec_b": "🚀 Calculate Target Cost",
        "exec_compare_b": "⚔️ Run 2-Supplier Benchmark & Cherry-Picking",
        "sub_p": "Quoted Price",
        "adj_p": "Target Cost",
        "diff_p": "Savings Potential",
        "diff_r": "Savings Ratio",
        "tbl_hdr": "📋 Standard Cost Sheet Audit Comparison (Target Reverse-Allocation)",
        "cols": ["Category", "Cost Item", "Submitted", "Target Cost", "Variance", "Audit Rationale & Action Plan"],
        "dl_csv": "📥 Download Target Cost Sheet (CSV)",
        "hist_hdr": "📊 Cumulative Cost Audit & Savings History",
        "hist_search_v": "Filter by Project",
        "hist_search_p": "Filter by Part No / Name",
        "hist_search_s": "Filter by Supplier",
        "hist_dl_csv": "📥 Download All History (CSV)",
        "hist_empty": "No audit history found. Audited quotes will be automatically recorded here.",
        "prompt_lang": "Provide the complete breakdown rationale, cost item cuts, and negotiation memo in ENGLISH.",
        "proc_options": {
            "프레스": "Press (Stamping)",
            "가공": "Machining (CNC)",
            "사출": "Plastic Injection",
            "소결": "Sintering",
            "다이캐스팅": "Die-Casting",
            "조립": "Assembly",
            "일반구매": "Standard Purchased Parts",
            "그 외": "Others"
        }
    },
    "中文": {
        "title": "📊 供应商报价审查、目标价反向核算及双供应商择优比价(Cherry-Picking)系统",
        "caption": "支持工艺稼动率、机械间接费分摊、首尔外汇中介基准汇率、目标价反向分解设计及两家供应商1:1交叉比价择优核算。",
        "settings": "⚙️ 审查及目标成本核算基准设置",
        "api_auto": "🔑 API Key 自动绑定成功",
        "api_input": "输入 Gemini API Key",
        "fx_header": "💱 基准币种与汇率设置",
        "cur_select": "选择适用币种",
        "cur_rate_label": "1 {cur} 对韩元汇率 (KRW)",
        "krw_info": "韩元(KRW)报价 (汇率 1.0)",
        "smbs_link": "🔗 首尔外汇中介(SMBS)每日汇率",
        "proj_header": "🚘 零件及项目履历信息",
        "v_type": "开发车型 / 项目代码 (Project)",
        "p_no": "零件号 (Part No.)",
        "p_name": "零件名称 (Part Name)",
        "target_p_label": "🎯 目标采购单价 (Target Price, 可选)",
        "target_p_help": "输入目标价时，系统自动反向倒推各成本明细项的削减额及技术降本措施。(输入0则为常规核算)",
        "proc_sel": "制造工艺选择",
        "eff_lbl": "设备效率上限基准 (建议 Max: {eff}%)",
        "labor_job": "官方标准工种: {job}",
        "labor_rate": "工时单价基准 (韩元/秒)",
        "et_rate": "宽放率 / ET率基准 (%)",
        "markup_hdr": "📑 费用加成率管控基准 (上限)",
        "mat_mgr": "材料管理费率上限 (%)",
        "mfg_oh": "制造间接费率上限 (对比人工费 %)",
        "admin_r": "一般管理费率上限 (%)",
        "profit_r": "利润率上限 (%)",
        "scrap_lbl": "废料实际变卖单价 (韩元/kg)",
        "tab_audit": "🔍 单个报价审查与目标价核算",
        "tab_compare": "⚔️ 双供应商比价与择优(Cherry-Picking)",
        "tab_history": "🕒 核价履历管理看板",
        "up_hdr": "📂 录入审查报价单 (支持多页/附件同时比对)",
        "paste_tab": "📋 剪贴板截图粘贴",
        "file_tab": "📁 文件批量上传",
        "paste_b": "📋 添加当前截图",
        "clear_b": "🗑️ 清空粘贴图片",
        "count_msg": "当前已登记截图: {count} 张",
        "file_up_lbl": "选择报价单图片 (支持多选)",
        "orig_hdr": "📄 原始报价单凭证 (共 {count} 页)",
        "res_hdr": "🔍 合理性审查及目标成本倒推",
        "api_warn": "👈 请在左侧侧边栏配置 Gemini API Key。",
        "exec_b": "🚀 自动核算目标成本核算单",
        "exec_compare_b": "⚔️ 执行双供应商对标比价及择优组合分析",
        "sub_p": "供应商提报单价",
        "adj_p": "我司目标核算单价",
        "diff_p": "预计降本金额",
        "diff_r": "降本比率",
        "tbl_hdr": "📋 标准成本核算对比表 (目标价反向分摊)",
        "cols": ["区分", "项目", "提报金额", "目标核算额", "差额(核减)", "核减理由及谈判主攻点"],
        "dl_csv": "📥 下载目标核算单 (CSV/Excel)",
        "hist_hdr": "📊 零件/车型累计核价与降本履历",
        "hist_search_v": "按车型/项目代码搜索",
        "hist_search_p": "按零件号/零件名搜索",
        "hist_search_s": "按供应商(协力社)搜索",
        "hist_dl_csv": "📥 下载完整履历 (CSV)",
        "hist_empty": "暂无保存的核价履历。核价分析执行后将自动记录至此看板。",
        "prompt_lang": "请使用简体中文输出详细的审查意见、剔除理由、倒推分摊依据及向供应商发送的官方谈判公文。",
        "proc_options": {
            "프레스": "冲压 (Press)",
            "가공": "机加工 (CNC)",
            "사출": "注塑 (Injection)",
            "소결": "粉末冶金/烧结 (Sintering)",
            "다이캐스팅": "压铸 (Die-Casting)",
            "조립": "总成组装 (Assembly)",
            "일반구매": "通用标准外购件",
            "그 외": "其他制造工艺"
        }
    }
}

# 3. 서울외환중개(SMBS) 환율 크롤링
@st.cache_data(ttl=3600)
def get_smbs_rates():
    rates = {"KRW": 1.0, "USD": 1360.0, "CNY": 195.0, "EUR": 1520.0, "INR": 16.5}
    url = "http://www.smbs.biz/ExRate/TodayExRate.jsp"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        html = urllib.request.urlopen(req, timeout=3.0).read().decode('euc-kr', 'ignore')
        tables = pd.read_html(io.StringIO(html))
        for t in tables:
            for _, row in t.iterrows():
                row_str = " ".join([str(val) for val in row.values])
                for cur in ["USD", "CNY", "EUR", "INR"]:
                    if cur in row_str:
                        m = re.findall(r'[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?', row_str)
                        for val in m:
                            clean_val = float(val.replace(",", ""))
                            if cur == "USD" and 1000 <= clean_val <= 2000:
                                rates["USD"] = clean_val
                                break
                            elif cur == "EUR" and 1000 <= clean_val <= 2200:
                                rates["EUR"] = clean_val
                                break
                            elif cur == "CNY" and 100 <= clean_val <= 300:
                                rates["CNY"] = clean_val
                                break
                            elif cur == "INR" and 10 <= clean_val <= 35:
                                rates["INR"] = clean_val
                                break
    except Exception:
        pass
    return rates

# 4. 공정별 내부 원가 산출 기준 데이터
IND_MAP = {
    "프레스": {"eff": 85, "job": "판금/프레스조작원", "rate": 4.04, "oh": 220},
    "가공": {"eff": 90, "job": "선반/CNC기계조작원", "rate": 4.11, "oh": 200},
    "사출": {"eff": 90, "job": "플라스틱사출기조작원", "rate": 3.65, "oh": 200},
    "소결": {"eff": 85, "job": "소성로/성형기조작원", "rate": 3.71, "oh": 200},
    "다이캐스팅": {"eff": 75, "job": "다이캐스트원/주조원", "rate": 3.69, "oh": 250},
    "조립": {"eff": 90, "job": "부품조립원/단순노무원", "rate": 3.66, "oh": 50},
    "일반구매": {"eff": 85, "job": "제조업 생산직 평균", "rate": 3.98, "oh": 100},
    "그 외": {"eff": 80, "job": "제조업 생산직 평균", "rate": 3.98, "oh": 100}
}

# 5. 사이드바 설정 영역
with st.sidebar:
    selected_lang = st.selectbox("🌐 Language / 언어 / 语言", ["한국어", "English", "中文"], index=0)
    txt = I18N[selected_lang]

    st.header(txt["settings"])

    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success(txt["api_auto"])
    else:
        api_key = st.text_input(txt["api_input"], type="password")

    st.divider()
    st.subheader(txt["fx_header"])
    all_rates = get_smbs_rates()
    selected_cur = st.selectbox(txt["cur_select"], ["KRW", "USD", "CNY", "EUR", "INR"], index=0)

    if selected_cur == "KRW":
        cur_rate = 1.0
        st.info(txt["krw_info"])
    else:
        init_val = float(all_rates.get(selected_cur, 1360.0 if selected_cur == "USD" else 1.0))
        cur_rate = st.number_input(
            txt["cur_rate_label"].format(cur=selected_cur),
            value=init_val,
            step=1.0 if selected_cur in ["USD", "EUR"] else 0.1,
            format="%.2f"
        )
        st.caption(f"ℹ️ 1 {selected_cur} = {cur_rate:,.2f} KRW")
        st.caption(f"[{txt['smbs_link']}](http://www.smbs.biz/ExRate/TodayExRate.jsp)")

    st.divider()
    st.subheader(txt["proj_header"])
    in_veh = st.text_input(txt["v_type"], placeholder="예: TB6S / TB7")
    in_pno = st.text_input(txt["p_no"], placeholder="예: 68000511010")
    in_pnm = st.text_input(txt["p_name"], placeholder="예: STATOR / FLANGE")

    target_price_input = st.number_input(
        txt["target_p_label"],
        min_value=0.0,
        value=0.0,
        step=1.0 if selected_cur == "KRW" else 0.01,
        format="%.3f" if selected_cur in ["USD", "CNY", "EUR"] else "%.1f",
        help=txt["target_p_help"]
    )
    if target_price_input > 0:
        st.success(f"🎯 Target Mode: {target_price_input} {selected_cur}")

    st.divider()
    proc_labels = list(txt["proc_options"].values())
    selected_proc_label = st.selectbox(txt["proc_sel"], proc_labels, index=0)
    internal_proc_key = [k for k, v in txt["proc_options"].items() if v == selected_proc_label][0]
    cfg = IND_MAP[internal_proc_key]

    std_eff = st.slider(txt["eff_lbl"].format(eff=cfg['eff']), 50, 95, cfg["eff"], 5)
    st.caption(txt["labor_job"].format(job=cfg['job']))
    std_rate = st.number_input(txt["labor_rate"], 1.0, 15.0, cfg["rate"], 0.1)
    std_et = st.slider(txt["et_rate"], 0, 35, 10, 1)

    st.subheader(txt["markup_hdr"])
    mat_r = st.slider(txt["mat_mgr"], 0.0, 10.0, 2.0, 0.5)
    oh_r = st.slider(txt["mfg_oh"], 20, 350, cfg["oh"], 10)
    adm_r = st.slider(txt["admin_r"], 1.0, 25.0, 15.0, 0.5)
    prf_r = st.slider(txt["profit_r"], 1.0, 20.0, 10.0, 0.5)

    scrap_p = st.number_input(txt["scrap_lbl"], min_value=0, value=12500, step=500)

# 6. 메인 레이아웃
st.title(txt["title"])
st.caption(txt["caption"])

tab_main1, tab_main2, tab_main3 = st.tabs([txt["tab_audit"], txt["tab_compare"], txt["tab_history"]])

# ==========================================
# TAB 1: 단일 견적 분석 & 목표가 역산
# ==========================================
with tab_main1:
    if "clip_imgs" not in st.session_state:
        st.session_state.clip_imgs = []
    if "paste_key_idx" not in st.session_state:
        st.session_state.paste_key_idx = 0

    st.write(f"### {txt['up_hdr']}")
    t1, t2 = st.tabs([txt["paste_tab"], txt["file_tab"]])

    imgs = []
    with t1:
        cb1, cb2 = st.columns([2, 1])
        with cb1:
            p_res = paste_image_button(
                txt["paste_b"],
                background_color="#1F4E79",
                text_color="#FFF",
                key=f"paste_btn_{selected_lang}_{st.session_state.paste_key_idx}"
            )
        with cb2:
            if st.button(txt["clear_b"], key="btn_clear_single"):
                st.session_state.clip_imgs = []
                st.session_state.paste_key_idx += 1
                st.rerun()

        if p_res.image_data is not None:
            buf = io.BytesIO()
            p_res.image_data.save(buf, format="PNG")
            nb = buf.getvalue()
            if not st.session_state.clip_imgs or st.session_state.clip_imgs[-1] != nb:
                st.session_state.clip_imgs.append(nb)

        if st.session_state.clip_imgs:
            imgs = st.session_state.clip_imgs
            st.info(txt["count_msg"].format(count=len(imgs)))

    with t2:
        u_files = st.file_uploader(txt["file_up_lbl"], type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="single_up_files")
        if u_files:
            imgs = [f.getvalue() for f in u_files]

    if imgs:
        col_l, col_r = st.columns([1, 1], gap="medium")
        with col_l:
            st.subheader(txt["orig_hdr"].format(count=len(imgs)))
            for i, b in enumerate(imgs):
                st.image(b, caption=f"Page {i+1}", use_container_width=True)

        with col_r:
            st.subheader(txt["res_hdr"])
            if not api_key:
                st.warning(txt["api_warn"])
            else:
                if st.button(txt["exec_b"], type="primary", key="btn_exec_single"):
                    with st.spinner("Analyzing quotes and computing target cost engineering..."):
                        client = genai.Client(api_key=api_key)
                        parts = [types.Part.from_bytes(data=b, mime_type="image/png") for b in imgs]

                        target_instruction = ""
                        if target_price_input > 0:
                            target_instruction = f"""
[🎯 최우선 특별 임무: 목표 타겟 단가({target_price_input} {selected_cur}) 맞춤형 역산 배분]
- 사용자가 최종 도달해야 할 Target Price를 '{target_price_input} {selected_cur}'로 지정했습니다.
- 따라서 최종 adjusted_price는 반드시 지정된 {target_price_input}에 수렴하도록 역산하십시오.
- 협력사 제출가와 타겟단가 사이의 총 절감 필요액을 원가 요소별로 합리적으로 배분하십시오.
"""
                        else:
                            target_instruction = "[표준 사정 모드] 당사 표준 사정 기준에 따라 과다 계상된 원가 항목을 삭감하고 합리적인 사정가를 도출하세요."

                        prompt_intro = f"""
당신은 자동차 소형 모터 구매팀 수석 원가 분석관입니다. 제공된 견적서 이미지를 정밀 분석하여 사정원가계산서를 작성하세요.
[입력정보] 차종: '{in_veh}', 품번: '{in_pno}', 품명: '{in_pnm}'
[기준통화] {selected_cur} (환율 기준: 1 {selected_cur} = {cur_rate} KRW)
[기본 사정 기준]
- 공정: {internal_proc_key}, 설비효율: {std_eff}% 이상 필수
- 임율: {std_rate}원/초 (협력사가 더 낮으면 협력사 임율 유지)
- 여유율: {std_et}%, 재료관리비: 순재료비의 {mat_r}% 이하
- 간접경비: 상한 {oh_r}%, 일반관리비: Min({adm_r}%, 협력사치), 영업이익: Min({prf_r}%, 협력사치)
- 스크랩: 매각단가 {scrap_p}원/kg (복합수지 사출 분쇄불가는 투입량 전체 인정, 금속은 환입 필수)
- 절대원칙: 총 사정단가가 협력사 제출단가보다 커지는 역전 현상 금지 (사정가 <= 제출가)

[🚨 핵심 심사 원칙 1: 소수점 자릿수 정밀도 보존]
- 견적서 원본에 표기된 제출단가의 소수점 자릿수를 정확히 파악하여 decimal_precision(정수면 0, 소수점 1자리 1, 2자리 2, 3자리 3)으로 반환하세요.
- 견적서가 정수로 제출되었으면 모든 단가도 정수로, 소수점 1자리까지만 있으면 1자리까지만 표기하도록 정합성을 맞추세요.

[🚨 핵심 심사 원칙 2: 재료비 산출 근거(원단가 미오픈) 강력 적발 및 경고]
- 자동차 부품 재료비의 기본 공식은 반드시 `(재료단가 × 투입중량) - (스크랩단가 × 스크랩중량)` 이어야 합니다.
- 만약 견적서에 원재료 단가(원/kg 등)나 투입중량/단중을 명시하지 않고 총액(금액)만 일방적으로 기재해 놓았을 경우:
  1) cost_breakdown의 재료비 'note' 열에 "⚠️ 재료단가 및 투입/스크랩 중량 미오픈(금액 산출 근거 불투명) - 정합성 검증 불가로 상세 원가내역서 필수 징구 대상"이라고 명기할 것.
  2) audit_comment 총평 및 네고 공문 첫 문단에 "원소재 단가 및 중량이 오픈되지 않아 재료비 적정성 판단이 불가능하므로, 원단가가 기재된 상세 을지 재제출 요구"를 강력히 포함할 것.

{target_instruction}

- 언어 지침: {txt['prompt_lang']}
"""
                        json_format_instruction = """
반드시 최상위가 단일 JSON Object 형태여야 합니다 (Array 금지):
{
  "item_info": {"vehicle_type": "", "supplier": "", "part_name": "", "part_no": "", "currency": "", "decimal_precision": 0},
  "comparison": {"submitted_price": 0.0, "adjusted_price": 0.0, "cost_reduction": 0.0, "reduction_rate": 0.0},
  "cost_breakdown": [
    {"category": "", "item": "", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""}
  ],
  "audit_comment": ""
}
"""
                        p_txt = prompt_intro + "\n" + json_format_instruction
                        parts.append(p_txt)

                        # 503 및 일시적 과부하 대응: Flash 모델 시도 후 실패 시 즉시 Pro 모델로 스위칭
                        candidate_models = ["gemini-3.6-flash", "gemini-3.1-pro-preview"]
                        data = None
                        last_error = None

                        for model_name in candidate_models:
                            if data is not None:
                                break
                            for attempt in range(2):
                                try:
                                    res = client.models.generate_content(
                                        model=model_name,
                                        contents=parts,
                                        config=types.GenerateContentConfig(response_mime_type="application/json")
                                    )
                                    c_raw = res.text.strip()
                                    c_raw = re.sub(r"^```json\s*", "", c_raw)
                                    c_raw = re.sub(r"^```\s*", "", c_raw)
                                    c_raw = re.sub(r"\s*```$", "", c_raw)
                                    raw_parsed = json.loads(c_raw, strict=False)

                                    if isinstance(raw_parsed, list):
                                        data = raw_parsed[0] if len(raw_parsed) > 0 and isinstance(raw_parsed[0], dict) else {}
                                    elif isinstance(raw_parsed, dict):
                                        data = raw_parsed
                                    else:
                                        data = {}
                                    break
                                except Exception as e:
                                    last_error = e
                                    time.sleep(1.5)

                        if data is None:
                            st.error(f"Error: {last_error}")
                        else:
                            item_info = data.get("item_info", {}) if isinstance(data.get("item_info"), dict) else {}
                            fv = in_veh or item_info.get("vehicle_type", "Unknown")
                            fp = in_pno or item_info.get("part_no", "Unknown")
                            fn = in_pnm or item_info.get("part_name", "Unknown")
                            fs = item_info.get("supplier", "Unknown")
                            detected_cur = item_info.get("currency", selected_cur)
                            dec_prec = int(item_info.get("decimal_precision", 0 if detected_cur == "KRW" else 3))

                            comp = data.get("comparison", {}) if isinstance(data.get("comparison"), dict) else {}
                            sub_p = float(comp.get("submitted_price", 0.0))
                            adj_p = float(comp.get("adjusted_price", 0.0))
                            red_p = float(comp.get("cost_reduction", 0.0))
                            red_r = float(comp.get("reduction_rate", 0.0))

                            h_file = "audit_history.csv"
                            row = pd.DataFrame([{
                                "일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "차종": fv, "품번": fp, "품명": fn, "협력사": fs, "공정": selected_proc_label,
                                "통화": detected_cur,
                                "제출가": round(sub_p, dec_prec),
                                "사정(목표)가": round(adj_p, dec_prec),
                                "절감액": round(red_p, dec_prec),
                                "절감율": round(red_r, 1)
                            }])
                            if os.path.exists(h_file):
                                row.to_csv(h_file, mode='a', header=False, index=False, encoding="utf-8-sig")
                            else:
                                row.to_csv(h_file, mode='w', header=True, index=False, encoding="utf-8-sig")

                            # 상단 지표 카드
                            m1, m2, m3, m4 = st.columns(4)
                            cur_unit = f" {detected_cur}"
                            m1.metric(txt["sub_p"], f"{fmt_price(sub_p, dec_prec)}{cur_unit}")
                            m2.metric(txt["adj_p"], f"{fmt_price(adj_p, dec_prec)}{cur_unit}")
                            m3.metric(txt["diff_p"], f"-{fmt_price(red_p, dec_prec)}{cur_unit}")
                            m4.metric(txt["diff_r"], f"-{red_r:.1f}%")

                            st.markdown(f"#### {txt['tbl_hdr']}")
                            breakdown_list = data.get("cost_breakdown", [])
                            if isinstance(breakdown_list, list) and len(breakdown_list) > 0:
                                df = pd.DataFrame(breakdown_list)
                                if len(df.columns) >= 6:
                                    df = df.iloc[:, :6]
                                    df.columns = txt["cols"]
                                    df[txt["cols"][2]] = df[txt["cols"][2]].apply(lambda x: fmt_price(x, dec_prec))
                                    df[txt["cols"][3]] = df[txt["cols"][3]].apply(lambda x: fmt_price(x, dec_prec))
                                    df[txt["cols"][4]] = df[txt["cols"][4]].apply(lambda x: fmt_price(x, dec_prec))
                                st.dataframe(df, use_container_width=True, hide_index=True)

                                st.download_button(
                                    txt["dl_csv"],
                                    df.to_csv(index=False, encoding="utf-8-sig"),
                                    f"Audit_{fp}.csv",
                                    "text/csv"
                                )
                            st.divider()
                            st.markdown(data.get("audit_comment", ""))

# ==========================================
# TAB 2: 2개사 견적 1:1 비교 & 체리피킹
# ==========================================
with tab_main2:
    st.subheader("⚔️ 협력사 2개사 견적 대조 및 체리피킹(Cherry-Picking) 최저 원가 도출")
    st.caption("동일 부품에 대해 두 업체의 견적서를 1:1로 맞대어 각 세부 항목별 최저가를 결합한 가상 최저단가(Best-of-Best) 및 상호 네고 논리를 산출합니다.")

    if "cmp_imgs_a" not in st.session_state:
        st.session_state.cmp_imgs_a = []
    if "cmp_imgs_b" not in st.session_state:
        st.session_state.cmp_imgs_b = []
    if "cmp_paste_idx_a" not in st.session_state:
        st.session_state.cmp_paste_idx_a = 0
    if "cmp_paste_idx_b" not in st.session_state:
        st.session_state.cmp_paste_idx_b = 0

    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        st.markdown("### 🏢 [업체 A] 견적서 등록")
        s_name_a = st.text_input("업체 A 이름", value="", placeholder="예: 모텍 / 업체 A")
        ca1, ca2 = st.tabs(["📋 붙여넣기", "📁 파일업로드"])
        imgs_a = []
        with ca1:
            p_a = paste_image_button("📋 A사 캡처 추가", background_color="#0F52BA", text_color="#FFF", key=f"paste_a_{st.session_state.cmp_paste_idx_a}")
            if st.button("🗑️ A사 초기화", key="clr_a"):
                st.session_state.cmp_imgs_a = []
                st.session_state.cmp_paste_idx_a += 1
                st.rerun()
            if p_a.image_data is not None:
                b = io.BytesIO()
                p_a.image_data.save(b, format="PNG")
                nb = b.getvalue()
                if not st.session_state.cmp_imgs_a or st.session_state.cmp_imgs_a[-1] != nb:
                    st.session_state.cmp_imgs_a.append(nb)
            if st.session_state.cmp_imgs_a:
                imgs_a = st.session_state.cmp_imgs_a
                st.info(f"A사 캡처: {len(imgs_a)}장")
        with ca2:
            up_a = st.file_uploader("A사 파일 선택", type=["png","jpg","jpeg"], accept_multiple_files=True, key="up_a")
            if up_a:
                imgs_a = [f.getvalue() for f in up_a]

        if imgs_a:
            for i, im in enumerate(imgs_a):
                st.image(im, caption=f"A사 Page {i+1}", use_container_width=True)

    with col_b:
        st.markdown("### 🏢 [업체 B] 견적서 등록")
        s_name_b = st.text_input("업체 B 이름", value="", placeholder="예: ZEB / 업체 B")
        cb1, cb2 = st.tabs(["📋 붙여넣기", "📁 파일업로드"])
        imgs_b = []
        with cb1:
            p_b = paste_image_button("📋 B사 캡처 추가", background_color="#B22222", text_color="#FFF", key=f"paste_b_{st.session_state.cmp_paste_idx_b}")
            if st.button("🗑️ B사 초기화", key="clr_b"):
                st.session_state.cmp_imgs_b = []
                st.session_state.cmp_paste_idx_b += 1
                st.rerun()
            if p_b.image_data is not None:
                b = io.BytesIO()
                p_b.image_data.save(b, format="PNG")
                nb = b.getvalue()
                if not st.session_state.cmp_imgs_b or st.session_state.cmp_imgs_b[-1] != nb:
                    st.session_state.cmp_imgs_b.append(nb)
            if st.session_state.cmp_imgs_b:
                imgs_b = st.session_state.cmp_imgs_b
                st.info(f"B사 캡처: {len(imgs_b)}장")
        with cb2:
            up_b = st.file_uploader("B사 파일 선택", type=["png","jpg","jpeg"], accept_multiple_files=True, key="up_b")
            if up_b:
                imgs_b = [f.getvalue() for f in up_b]

        if imgs_b:
            for i, im in enumerate(imgs_b):
                st.image(im, caption=f"B사 Page {i+1}", use_container_width=True)

    st.divider()
    if not (imgs_a and imgs_b):
        st.warning("👈 A사와 B사의 견적서 이미지를 각각 1장 이상 등록해야 체리피킹 비교가 가능합니다.")
    else:
        if st.button(txt["exec_compare_b"], type="primary", key="btn_exec_compare"):
            if not api_key:
                st.warning(txt["api_warn"])
            else:
                with st.spinner("2개사 견적서 교차 대조 및 체리피킹 최적 원가 분석 중..."):
                    client = genai.Client(api_key=api_key)
                    parts_cmp = []
                    parts_cmp.append("=== [업체 A 견적서 이미지들 시작] ===")
                    for b in imgs_a:
                        parts_cmp.append(types.Part.from_bytes(data=b, mime_type="image/png"))
                    parts_cmp.append("=== [업체 B 견적서 이미지들 시작] ===")
                    for b in imgs_b:
                        parts_cmp.append(types.Part.from_bytes(data=b, mime_type="image/png"))

                    prompt_cmp = f"""
당신은 자동차 소형 모터 구매팀의 수석 원가 분석관입니다.
동일 부품에 대해 제출된 [업체 A]와 [업체 B]의 견적서를 1:1로 정밀 교차 비교하고 '체리피킹(Cherry-Picking) 최저 원가'를 도출하십시오.

[사전 정보]
- 프로젝트/차종: '{in_veh}', 품번: '{in_pno}', 품명: '{in_pnm}'
- 공정: {internal_proc_key}
- 기준통화: {selected_cur} (1 {selected_cur} = {cur_rate} KRW)
- 업체 A 명칭: '{s_name_a or "A사"}'
- 업체 B 명칭: '{s_name_b or "B사"}'

[핵심 분석 및 체리피킹 지침]
1. 양사의 원가 항목(순재료비, 가공비/C/T, 일반관리비, 이윤, 포장운반비 등)을 완벽히 1:1 매칭하여 비교표를 작성하세요.
2. 재료비 산출 근거(재료단가 및 중량)가 오픈되었는지 확인하고, 미오픈된 업체가 있다면 비고란에 강력한 시정 요구를 기재하세요.
3. 견적서 원본의 소수점 자릿수 정합성(decimal_precision)을 파악하여 반영하세요.
4. 각 세부 항목별로 더 저렴한 쪽의 단가와 합리적인 근거를 채택하여 '체리피킹 최저단가'를 산출하세요.
5. 양방향 네고 공문 작성 (A사 대상, B사 대상).
6. 언어: {txt['prompt_lang']}

[JSON 응답 규격]
반드시 최상위가 단일 JSON Object 형태여야 합니다:
{{
  "summary": {{
    "supplier_a": "{s_name_a or 'A사'}",
    "supplier_b": "{s_name_b or 'B사'}",
    "total_a": 0.0,
    "total_b": 0.0,
    "cherry_pick_total": 0.0,
    "currency": "{selected_cur}",
    "decimal_precision": 0
  }},
  "comparison_table": [
    {{
      "item": "원가항목명",
      "price_a": 0.0,
      "price_b": 0.0,
      "diff": 0.0,
      "cherry_pick_winner": "A사 또는 B사",
      "cherry_pick_price": 0.0,
      "rationale": "비교 분석 내용 및 체리피킹 사유"
    }}
  ],
  "nego_for_a": "A사에 보낼 기술적 네고 요구 공문",
  "nego_for_b": "B사에 보낼 기술적 네고 요구 공문"
}}
"""
                    parts_cmp.append(prompt_cmp)

                    candidate_models = ["gemini-3.6-flash", "gemini-3.1-pro-preview"]
                    cmp_data = None
                    last_cmp_err = None

                    for model_name in candidate_models:
                        if cmp_data is not None:
                            break
                        for attempt in range(2):
                            try:
                                res = client.models.generate_content(
                                    model=model_name,
                                    contents=parts_cmp,
                                    config=types.GenerateContentConfig(response_mime_type="application/json")
                                )
                                c_raw = res.text.strip()
                                c_raw = re.sub(r"^```json\s*", "", c_raw)
                                c_raw = re.sub(r"^```\s*", "", c_raw)
                                c_raw = re.sub(r"\s*```$", "", c_raw)
                                cmp_data = json.loads(c_raw, strict=False)
                                break
                            except Exception as e:
                                last_cmp_err = e
                                time.sleep(1.5)

                    if cmp_data is None:
                        st.error(f"비교 분석 중 오류 발생: {last_cmp_err}")
                    else:
                        summ = cmp_data.get("summary", {})
                        tot_a = float(summ.get("total_a", 0.0))
                        tot_b = float(summ.get("total_b", 0.0))
                        tot_cp = float(summ.get("cherry_pick_total", 0.0))
                        cur_str = f" {summ.get('currency', selected_cur)}"
                        cmp_prec = int(summ.get("decimal_precision", 0 if selected_cur == "KRW" else 3))

                        sa_name = summ.get("supplier_a", "A사")
                        sb_name = summ.get("supplier_b", "B사")

                        st.success("🎯 2개사 견적 대조 및 체리피킹 최적가 산출 완료")
                        mc1, mc2, mc3, mc4 = st.columns(4)
                        mc1.metric(f"🏢 {sa_name} 견적", f"{fmt_price(tot_a, cmp_prec)}{cur_str}")
                        mc2.metric(f"🏢 {sb_name} 견적", f"{fmt_price(tot_b, cmp_prec)}{cur_str}")
                        mc3.metric("🍒 체리피킹 최저단가", f"{fmt_price(tot_cp, cmp_prec)}{cur_str}")
                        gap_val = min(tot_a, tot_b) - tot_cp
                        mc4.metric("추가 절감 잠재액", f"-{fmt_price(gap_val, cmp_prec)}{cur_str}")

                        st.markdown("#### 📋 세부 원가 항목 1:1 대조 및 체리피킹 표")
                        c_table = cmp_data.get("comparison_table", [])
                        if c_table:
                            df_cmp = pd.DataFrame(c_table)
                            if len(df_cmp.columns) >= 7:
                                df_cmp = df_cmp.iloc[:, :7]
                                df_cmp.columns = ["원가 항목", f"{sa_name} 견적", f"{sb_name} 견적", "차액 (A-B)", "채택 업체", "체리피킹 단가", "비교 분석 및 채택 사유"]
                                df_cmp[f"{sa_name} 견적"] = df_cmp[f"{sa_name} 견적"].apply(lambda x: fmt_price(x, cmp_prec))
                                df_cmp[f"{sb_name} 견적"] = df_cmp[f"{sb_name} 견적"].apply(lambda x: fmt_price(x, cmp_prec))
                                df_cmp["차액 (A-B)"] = df_cmp["차액 (A-B)"].apply(lambda x: fmt_price(x, cmp_prec))
                                df_cmp["체리피킹 단가"] = df_cmp["체리피킹 단가"].apply(lambda x: fmt_price(x, cmp_prec))
                            st.dataframe(df_cmp, use_container_width=True, hide_index=True)

                            st.download_button(
                                "📥 2개사 견적 비교 및 체리피킹 대조표 CSV 다운로드",
                                df_cmp.to_csv(index=False, encoding="utf-8-sig"),
                                f"CherryPick_Compare_{in_pno or 'Part'}.csv",
                                "text/csv"
                            )

                        st.divider()
                        nc1, nc2 = st.columns(2)
                        with nc1:
                            st.markdown(f"#### ✉️ [{sa_name}] 발송용 타격 네고 공문")
                            st.info(cmp_data.get("nego_for_a", ""))
                        with nc2:
                            st.markdown(f"#### ✉️ [{sb_name}] 발송용 타격 네고 공문")
                            st.info(cmp_data.get("nego_for_b", ""))

# ==========================================
# TAB 3: 이력 관리 대시보드
# ==========================================
with tab_main3:
    st.subheader(txt["hist_hdr"])
    h_file = "audit_history.csv"
    if os.path.exists(h_file):
        try:
            hdf = pd.read_csv(h_file, encoding="utf-8-sig")

            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                q_v = st.text_input(txt["hist_search_v"], "")
            with fc2:
                q_p = st.text_input(txt["hist_search_p"], "")
            with fc3:
                q_s = st.text_input(txt["hist_search_s"], "")

            res_df = hdf
            if q_v and "차종" in res_df.columns:
                res_df = res_df[res_df["차종"].astype(str).str.contains(q_v, na=False, case=False)]
            if q_p:
                cond = pd.Series([False] * len(res_df), index=res_df.index)
                if "품번" in res_df.columns:
                    cond |= res_df["품번"].astype(str).str.contains(q_p, na=False, case=False)
                if "품명" in res_df.columns:
                    cond |= res_df["품명"].astype(str).str.contains(q_p, na=False, case=False)
                res_df = res_df[cond]
            if q_s and "협력사" in res_df.columns:
                res_df = res_df[res_df["협력사"].astype(str).str.contains(q_s, na=False, case=False)]

            st.dataframe(res_df, use_container_width=True, hide_index=True)
            st.download_button(
                txt["hist_dl_csv"],
                hdf.to_csv(index=False, encoding="utf-8-sig"),
                "All_Audit_History.csv",
                "text/csv"
            )
        except Exception as e:
            st.error(f"Error loading history: {e}")
            if st.button("Reset History File"):
                os.remove(h_file)
                st.rerun()
    else:
        st.info(txt["hist_empty"])
