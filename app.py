import streamlit as st
import io, time, os, re, json, urllib.request
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

# 1. 페이지 설정
st.set_page_config(page_title="Cost Sheet Audit System", page_icon="📊", layout="wide")

# 2. 다국어 텍스트 사전 및 공정 매핑
I18N = {
    "한국어": {
        "title": "📊 협력사 견적/원가계산서 타당성 자동 분석 및 사정 견적",
        "caption": "공정별 설비효율, 기계경비 배부율, SMBS 환율, 다중 견적서(갑/을지) 교차검증 및 차종/품번 이력 관리를 지원합니다.",
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
        "tab_audit": "🔍 견적 분석 및 사정",
        "tab_history": "🕒 사정 이력 대시보드",
        "up_hdr": "📂 견적서 등록 (갑지/을지 다중 등록 가능)",
        "paste_tab": "📋 클립보드 붙여넣기",
        "file_tab": "📁 파일 업로드",
        "paste_b": "📋 캡처 추가하기",
        "clear_b": "🗑️ 붙여넣기 초기화",
        "count_msg": "등록된 캡처본: {count}장",
        "file_up_lbl": "이미지 파일 선택 (다중 선택 가능)",
        "orig_hdr": "📄 대상 견적서 ({count}장)",
        "res_hdr": "🔍 분석 및 사정 견적",
        "api_warn": "👈 사이드바에 API Key를 설정해주세요.",
        "exec_b": "🚀 사정 원가계산서 산출",
        "sub_p": "협력사 제출가",
        "adj_p": "당사 사정가",
        "diff_p": "절감 가능액",
        "diff_r": "절감율",
        "tbl_hdr": "📋 표준 견적 대조표",
        "cols": ["구분", "항목", "제출가", "사정가", "차액", "사정 기준 및 사유"],
        "dl_csv": "📥 사정 원가계산서 CSV 다운로드",
        "hist_hdr": "📊 부품/차종별 누적 원가 사정 이력",
        "hist_total_cnt": "총 검토 건수",
        "hist_total_sub": "총 제출가 합계",
        "hist_total_adj": "총 사정가 합계",
        "hist_total_sav": "총 절감 기여액",
        "hist_search_v": "차종 검색",
        "hist_search_p": "품번/품명 검색",
        "hist_dl_csv": "📥 전체 이력 CSV 다운로드",
        "hist_empty": "저장된 사정 이력이 없습니다. 견적서 분석을 실행하면 자동으로 누적 기록됩니다.",
        "prompt_lang": "한국어로 상세하고 전문적인 원가 검토 의견 및 협력사 공식 네고 문구를 작성하세요.",
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
        "title": "📊 Supplier Cost Sheet Audit & Target Cost System",
        "caption": "Supports equipment efficiency, overhead allocation, SMBS FX rates, multi-sheet audit, and project/part history tracking.",
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
        "proc_sel": "Select Manufacturing Process",
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
        "tab_audit": "🔍 Cost Audit & Target Price",
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
        "sub_p": "Quoted Price",
        "adj_p": "Target Cost",
        "diff_p": "Savings Potential",
        "diff_r": "Savings Ratio",
        "tbl_hdr": "📋 Standard Cost Sheet Audit Comparison",
        "cols": ["Category", "Cost Item", "Submitted", "Target Cost", "Variance", "Audit Remarks"],
        "dl_csv": "📥 Download Target Cost Sheet (CSV)",
        "hist_hdr": "📊 Cumulative Cost Audit & Savings History",
        "hist_total_cnt": "Total Audits",
        "hist_total_sub": "Total Submitted Amount",
        "hist_total_adj": "Total Target Amount",
        "hist_total_sav": "Total Savings Amount",
        "hist_search_v": "Filter by Project",
        "hist_search_p": "Filter by Part No / Part Name",
        "hist_dl_csv": "📥 Download All History (CSV)",
        "hist_empty": "No audit history found. Audited quotes will be automatically recorded here.",
        "prompt_lang": "Provide the complete breakdown rationale and negotiation memo in ENGLISH.",
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
        "title": "📊 供应商报价/成本核算单审查与目标成本系统",
        "caption": "支持工艺稼动率、机械间接费分摊、首尔外汇中介基准汇率、多页报价交叉验证及车型/零件履历管理。",
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
        "tab_audit": "🔍 报价审查与核算",
        "tab_history": "🕒 核价履历管理看板",
        "up_hdr": "📂 录入审查报价单 (支持多页/附件同时比对)",
        "paste_tab": "📋 剪贴板截图粘贴",
        "file_tab": "📁 文件批量上传",
        "paste_b": "📋 添加当前截图",
        "clear_b": "🗑️ 清空粘贴图片",
        "count_msg": "当前已登记截图: {count} 张",
        "file_up_lbl": "选择报价单图片 (支持多选)",
        "orig_hdr": "📄 原始报价单凭证 (共 {count} 页)",
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
        "hist_total_cnt": "总审核笔数",
        "hist_total_sub": "提报总金额",
        "hist_total_adj": "目标总金额",
        "hist_total_sav": "累计降本总额",
        "hist_search_v": "按车型/项目代码搜索",
        "hist_search_p": "按零件号/零件名搜索",
        "hist_dl_csv": "📥 下载完整履历 (CSV)",
        "hist_empty": "暂无保存的核价履历。核价分析执行后将自动记录至此看板。",
        "prompt_lang": "请使用简体中文输出详细的审查意见、剔除理由及向供应商发送的官方谈判公文。",
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

    st.divider()
    # 공정명 다국어 드롭다운 매핑
    proc_labels = list(txt["proc_options"].values())
    selected_proc_label = st.selectbox(txt["proc_sel"], proc_labels, index=0)
    # 선택된 라벨로부터 내부 키값(한국어 기준 키) 역추출
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

tab_main1, tab_main2 = st.tabs([txt["tab_audit"], txt["tab_history"]])

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
            # key에 언어명(selected_lang)을 부여하여 언어 변경 시 캡처 버튼 텍스트가 즉시 갱신되도록 처리
            p_res = paste_image_button(
                txt["paste_b"],
                background_color="#1F4E79",
                text_color="#FFF",
                key=f"paste_btn_{selected_lang}_{st.session_state.paste_key_idx}"
            )
        with cb2:
            if st.button(txt["clear_b"]):
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
        u_files = st.file_uploader(txt["file_up_lbl"], type=["png", "jpg", "jpeg"], accept_multiple_files=True)
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
                if st.button(txt["exec_b"], type="primary"):
                    with st.spinner("Analyzing quotes and calculating target cost..."):
                        client = genai.Client(api_key=api_key)
                        parts = [types.Part.from_bytes(data=b, mime_type="image/png") for b in imgs]

                        prompt_intro = f"""
당신은 자동차 부품 구매팀 원가 분석관입니다. 제공된 견적서 이미지를 정밀 분석하여 사정원가계산서를 작성하세요.
[입력정보] 차종: '{in_veh}', 품번: '{in_pno}', 품명: '{in_pnm}'
[기준통화] {selected_cur} (환율 기준: 1 {selected_cur} = {cur_rate} KRW)
[사정기준]
- 공정: {internal_proc_key}, 설비효율: {std_eff}% 이상 필수
- 임율: {std_rate}원/초 (협력사가 더 낮으면 협력사 임율 유지)
- 여유율: {std_et}%, 재료관리비: 순재료비의 {mat_r}% 이하
- 간접경비: 상한 {oh_r}%, 일반관리비: Min({adm_r}%, 협력사치), 영업이익: Min({prf_r}%, 협력사치)
- 스크랩: 매각단가 {scrap_p}원/kg (복합수지 사출 분쇄불가는 투입량 전체 인정, 금속은 환입 필수)
- 절대원칙: 총 사정단가가 협력사 제출단가보다 커지는 역전 현상 금지 (사정가 <= 제출가)
- 통화 주의: 원본 견적서가 RMB/위안 또는 외화인 경우 제출 단가 통화 규격을 유지하여 비교하고, 필요시 환율을 명기하세요.
- 언어 지침: {txt['prompt_lang']}
"""
                        json_format_instruction = """
반드시 최상위가 단일 JSON Object 형태여야 합니다 (Array 금지):
{
  "item_info": {"vehicle_type": "", "supplier": "", "part_name": "", "part_no": "", "currency": ""},
  "comparison": {"submitted_price": 0.0, "adjusted_price": 0.0, "cost_reduction": 0.0, "reduction_rate": 0.0},
  "cost_breakdown": [
    {"category": "", "item": "", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""}
  ],
  "audit_comment": ""
}
"""
                        p_txt = prompt_intro + "\n" + json_format_instruction
                        parts.append(p_txt)

                        data = None
                        last_error = None

                        for attempt in range(4):
                            try:
                                res = client.models.generate_content(
                                    model="gemini-3.6-flash",
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
                                err_str = str(e)
                                if any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]):
                                    time.sleep(3 * (attempt + 1))
                                    continue
                                else:
                                    break

                        if data is None:
                            st.error(f"Error: {last_error}")
                        else:
                            item_info = data.get("item_info", {}) if isinstance(data.get("item_info"), dict) else {}
                            fv = in_veh or item_info.get("vehicle_type", "Unknown")
                            fp = in_pno or item_info.get("part_no", "Unknown")
                            fn = in_pnm or item_info.get("part_name", "Unknown")
                            fs = item_info.get("supplier", "Unknown")
                            detected_cur = item_info.get("currency", selected_cur)

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
                                "제출가": round(sub_p, 3),
                                "사정가": round(adj_p, 3),
                                "절감액": round(red_p, 3),
                                "절감율": round(red_r, 1)
                            }])
                            if os.path.exists(h_file):
                                row.to_csv(h_file, mode='a', header=False, index=False, encoding="utf-8-sig")
                            else:
                                row.to_csv(h_file, mode='w', header=True, index=False, encoding="utf-8-sig")

                            m1, m2, m3, m4 = st.columns(4)
                            cur_unit = f" {detected_cur}"
                            m1.metric(txt["sub_p"], f"{sub_p:,.3f}{cur_unit}")
                            m2.metric(txt["adj_p"], f"{adj_p:,.3f}{cur_unit}")
                            m3.metric(txt["diff_p"], f"-{red_p:,.3f}{cur_unit}")
                            m4.metric(txt["diff_r"], f"-{red_r:.1f}%")

                            st.markdown(f"#### {txt['tbl_hdr']}")
                            breakdown_list = data.get("cost_breakdown", [])
                            if isinstance(breakdown_list, list) and len(breakdown_list) > 0:
                                df = pd.DataFrame(breakdown_list)
                                if len(df.columns) >= 6:
                                    df = df.iloc[:, :6]
                                    df.columns = txt["cols"]
                                st.dataframe(df, use_container_width=True, hide_index=True)

                                st.download_button(
                                    txt["dl_csv"],
                                    df.to_csv(index=False, encoding="utf-8-sig"),
                                    f"Audit_{fp}.csv",
                                    "text/csv"
                                )
                            st.divider()
                            st.markdown(data.get("audit_comment", ""))

# TAB 2: 이력 관리 대시보드
with tab_main2:
    st.subheader(txt["hist_hdr"])
    h_file = "audit_history.csv"
    if os.path.exists(h_file):
        try:
            hdf = pd.read_csv(h_file, encoding="utf-8-sig")
            col_sub = "제출가" if "제출가" in hdf.columns else "제출가(원)"
            col_adj = "사정가" if "사정가" in hdf.columns else "사정가(원)"
            col_sav = "절감액" if "절감액" in hdf.columns else "절감액(원)"

            c1, c2, c3, c4 = st.columns(4)
            c1.metric(txt["hist_total_cnt"], f"{len(hdf)} 건 / Cases")
            c2.metric(txt["hist_total_sub"], f"{pd.to_numeric(hdf[col_sub], errors='coerce').fillna(0).sum():,.0f}")
            c3.metric(txt["hist_total_adj"], f"{pd.to_numeric(hdf[col_adj], errors='coerce').fillna(0).sum():,.0f}")
            c4.metric(txt["hist_total_sav"], f"-{pd.to_numeric(hdf[col_sav], errors='coerce').fillna(0).sum():,.0f}")

            st.divider()
            fc1, fc2 = st.columns(2)
            with fc1:
                q_v = st.text_input(txt["hist_search_v"], "")
            with fc2:
                q_p = st.text_input(txt["hist_search_p"], "")

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
