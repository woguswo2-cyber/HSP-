import streamlit as st
import io, time, os, re, json, urllib.request
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

# 1. 페이지 설정
st.set_page_config(page_title="구매 견적 타당성 검토", page_icon="📊", layout="wide")

# 2. 환율 크롤링
@st.cache_data(ttl=3600)
def get_fx_rates():
    d = {"USD": 1380.0, "CNY": 192.0, "EUR": 1500.0, "INR": 16.5}
    try:
        req = urllib.request.Request("http://www.smbs.biz/ExRate/TodayExRate.jsp", headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=2.5).read().decode('euc-kr', 'ignore')
        for c in ["USD", "CNY", "EUR", "INR"]:
            m = re.search(c + r'.*?([0-9,]+\.[0-9]+|[0-9,]+)', html, re.DOTALL)
            if m:
                d[c] = float(m.group(1).replace(",", ""))
    except Exception:
        pass
    return d

# 3. 공정 데이터
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

# 4. 사이드바 설정
with st.sidebar:
    lang = st.selectbox("🌐 Language", ["한국어", "English", "中文"], index=0)
    st.header("⚙️ 분석 기준 설정")
    
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 API Key 자동 연동")
    else:
        api_key = st.text_input("Gemini API Key", type="password")
        
    st.divider()
    st.subheader("💱 SMBS 기준 환율")
    fx = get_fx_rates()
    c1, c2 = st.columns(2)
    with c1:
        r_usd = st.number_input("USD", value=float(fx["USD"]), step=1.0)
        r_cny = st.number_input("CNY", value=float(fx["CNY"]), step=0.5)
    with c2:
        r_eur = st.number_input("EUR", value=float(fx["EUR"]), step=1.0)
        r_inr = st.number_input("INR", value=float(fx["INR"]), step=0.1)

    st.divider()
    st.subheader("🚘 부품/프로젝트 정보")
    in_veh = st.text_input("차종 (Project)", placeholder="예: TB6S")
    in_pno = st.text_input("품번 (Part No.)", placeholder="예: 68000511010")
    in_pnm = st.text_input("품명 (Part Name)", placeholder="예: SHAFT")

    st.divider()
    ind = st.selectbox("공정 선택", list(IND_MAP.keys()), index=0)
    cfg = IND_MAP[ind]
    
    std_eff = st.slider(f"설비 효율 (Max {cfg['eff']}%)", 50, 95, cfg["eff"], 5)
    std_rate = st.number_input(f"임율 원/초 ({cfg['job']})", 1.0, 15.0, cfg["rate"], 0.1)
    std_et = st.slider("여유율/ET율 (%)", 0, 35, 10, 1)

    st.subheader("📑 가산율 상한")
    mat_r = st.slider("재료관리비율 (%)", 0.0, 10.0, 2.0, 0.5)
    oh_r = st.slider("간접제조경비율 (%)", 20, 350, cfg["oh"], 10)
    adm_r = st.slider("일반관리비율 (%)", 1.0, 25.0, 15.0, 0.5)
    prf_r = st.slider("영업이익율 (%)", 1.0, 20.0, 10.0, 0.5)
    
    scrap_p = st.number_input("실 스크랩 매각가 (원/kg)", min_value=0, value=12500, step=500)

# 5. 메인 레이아웃
st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 및 사정 견적")
tab_main1, tab_main2 = st.tabs(["🔍 견적 분석 및 사정", "🕒 사정 이력 대시보드"])

with tab_main1:
    if "clip_imgs" not in st.session_state:
        st.session_state.clip_imgs = []

    st.write("### 📂 견적서 등록 (갑지/을지 다중 등록 가능)")
    t1, t2 = st.tabs(["📋 클립보드 붙여넣기", "📁 파일 업로드"])
    
    imgs = []
    with t1:
        cb1, cb2 = st.columns([2, 1])
        with cb1:
            p_res = paste_image_button("📋 캡처 추가하기", background_color="#1F4E79", text_color="#FFF")
        with cb2:
            if st.button("🗑️ 붙여넣기 초기화"):
                st.session_state.clip_imgs = []
                st.rerun()
        if p_res.image_data is not None:
            buf = io.BytesIO()
            p_res.image_data.save(buf, format="PNG")
            nb = buf.getvalue()
            if not st.session_state.clip_imgs or st.session_state.clip_imgs[-1] != nb:
                st.session_state.clip_imgs.append(nb)
        if st.session_state.clip_imgs:
            imgs = st.session_state.clip_imgs
            st.info(f"등록된 캡처본: {len(imgs)}장")

    with t2:
        u_files = st.file_uploader("이미지 파일 선택", type=["png","jpg","jpeg"], accept_multiple_files=True)
        if u_files:
            imgs = [f.getvalue() for f in u_files]

    if imgs:
        col_l, col_r = st.columns([1, 1], gap="medium")
        with col_l:
            st.subheader(f"📄 대상 견적서 ({len(imgs)}장)")
            for i, b in enumerate(imgs):
                st.image(b, caption=f"Page {i+1}", use_container_width=True)
        
        with col_r:
            st.subheader("🔍 분석 및 사정 견적")
            if not api_key:
                st.warning("👈 왼쪽 사이드바에 API Key를 설정해주세요.")
            else:
                if st.button("🚀 사정 원가계산서 산출", type="primary"):
                    with st.spinner("AI 분석 중..."):
                        client = genai.Client(api_key=api_key)
                        parts = [types.Part.from_bytes(data=b, mime_type="image/png") for b in imgs]
                        
                        p_txt = f"""
                        자동차 부품 구매팀 원가 분석관으로서 견적서 이미지를 정밀 분석하여 사정원가계산서를 작성하세요.
                        [입력정보] 차종:'{in_veh}', 품번:'{in_pno}', 품명:'{in_pnm}'
                        [기준환율] USD:{r_usd}, CNY:{r_cny}, EUR:{r_eur}, INR:{r_inr} KRW
                        [사정기준]
                        - 공정: {ind}, 설비효율: {std_eff}% 이상 필수
                        - 임율: {std_rate}원/초 (협력사가 더 낮으면 협력사 임율 유지)
                        - 여유율: {std_et}%, 재료관리비: 순재료비의 {mat_r}% 이하
                        - 간접경비: 상한 {oh_r}%, 일반관리비: Min({adm_r}%, 협력사치), 영업이익: Min({prf_r}%, 협력사치)
                        - 스크랩: 매각단가 {scrap_p}원/kg (복합수지 사출 분쇄불가는 투입량 전체 인정, 금속은 환입 필수)
                        - 절대원칙: 총 사정단가가 협력사 제출단가보다 커지는 역전 현상 금지 (사정가 <= 제출가)
                        - 언어: {lang}로 audit_comment 작성

                        반드시 아래 JSON 포맷으로만 응답:
                        {{
                            "item_info": {{"vehicle_type": "", "supplier": "", "part_name": "", "part_no": ""}},
                            "comparison": {{"submitted_price": 0.0, "adjusted_price": 0.0, "cost_reduction": 0.0, "reduction_rate": 0.0}},
                            "cost_breakdown": [
                                {{"category": "", "item": "", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""}}
                            ],
                            "audit_comment": ""
                        }}
                        """
                        parts.append(p_txt)
                        
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
                            data = json.loads(c_raw, strict=False)

                            fv = in_veh or data.get("item_info", {}).get("vehicle_type", "Unknown")
                            fp = in_pno or data.get("item_info", {}).get("part_no", "Unknown")
                            fn = in_pnm or data.get("item_info", {}).get("part_name", "Unknown")
                            fs = data.get("item_info", {}).get("supplier", "Unknown")
                            comp = data["comparison"]

                            # 이력 CSV 기록
                            h_file = "audit_history.csv"
                            row = pd.DataFrame([{
                                "일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "차종": fv, "품번": fp, "품명": fn, "협력사": fs, "공정": ind,
                                "제출가": round(comp['submitted_price'], 1),
                                "사정가": round(comp['adjusted_price'], 1),
                                "절감액": round(comp['cost_reduction'], 1),
                                "절감율": round(comp['reduction_rate'], 1)
                            }])
                            if os.path.exists(h_file):
                                row.to_csv(h_file, mode='a', header=False, index=False, encoding="utf-8-sig")
                            else:
                                row.to_csv(h_file, mode='w', header=True, index=False, encoding="utf-8-sig")

                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("제출가", f"{comp['submitted_price']:,.1f}")
                            m2.metric("사정가", f"{comp['adjusted_price']:,.1f}")
                            m3.metric("절감액", f"-{comp['cost_reduction']:,.1f}")
                            m4.metric("절감율", f"-{comp['reduction_rate']:.1f}%")

                            st.markdown("#### 📋 표준 견적 대조표")
                            df = pd.DataFrame(data["cost_breakdown"])
                            df.columns = ["구분", "항목", "제출가", "사정가", "차액", "사정 기준 및 사유"]
                            st.dataframe(df, use_container_width=True, hide_index=True)

                            st.download_button(
                                "📥 사정 원가계산서 CSV 다운로드",
                                df.to_csv(index=False, encoding="utf-8-sig"),
                                f"Audit_{fp}.csv",
                                "text/csv"
                            )
                            st.divider()
                            st.markdown(data.get("audit_comment", ""))
                        except Exception as e:
                            st.error(f"오류 발생: {e}")

# TAB 2: 이력 관리
with tab_main2:
    st.subheader("📊 부품/차종별 누적 원가 사정 이력")
    h_file = "audit_history.csv"
    if os.path.exists(h_file):
        hdf = pd.read_csv(h_file, encoding="utf-8-sig")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 검토 건수", f"{len(hdf)} 건")
        c2.metric("총 제출가 합계", f"{hdf['제출가'].sum():,.0f} 원")
        c3.metric("총 사정가 합계", f"{hdf['사정가'].sum():,.0f} 원")
        c4.metric("총 절감 기여액", f"-{hdf['절감액'].sum():,.0f} 원")
        
        st.divider()
        fc1, fc2 = st.columns(2)
        with fc1:
            q_v = st.text_input("차종 검색", "")
        with fc2:
            q_p = st.text_input("품번/품명 검색", "")
            
        res_df = hdf
        if q_v:
            res_df = res_df[res_df["차종"].astype(str).str.contains(q_v, na=False, case=False)]
        if q_p:
            c_p = res_df["품번"].astype(str).str.contains(q_p, na=False, case=False)
            c_n = res_df["품명"].astype(str).str.contains(q_p, na=False, case=False)
            res_df = res_df[c_p | c_n]
            
        st.dataframe(res_df, use_container_width=True, hide_index=True)
        st.download_button(
            "📥 전체 이력 CSV 다운로드",
            hdf.to_csv(index=False, encoding="utf-8-sig"),
            "All_Audit_History.csv",
            "text/csv"
        )
    else:
        st.info("저장된 사정 이력이 없습니다. 견적서 분석을 실행하면 자동으로 누적 기록됩니다.")
