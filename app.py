import streamlit as st
import io
import time
import pandas as pd
import json
import re
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

# ---------------------------------------------------------
# 1. 페이지 레이아웃
# ---------------------------------------------------------
st.set_page_config(
    page_title="구매 견적/원가계산서 타당성 자동 검토",
    page_icon="📊",
    layout="wide"
)

st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 및 사정 견적 산출")
st.caption("제출 견적을 분석하여 당사 표준 원가 기준이 적용된 '적정 사정 원가계산서'를 자동 생성하고 엑셀로 다운로드합니다.")

# ---------------------------------------------------------
# 2. 공정별 표준 데이터 맵 (Max 설비효율 & 중기중앙회 공인 임율)
#    * 8시간/일 = 28,800초 기준 초당 임율 환산치
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "프레스": {"max_eff": 85, "job_name": "판금/프레스조작원", "sec_rate": 4.04},
    "가공": {"max_eff": 90, "job_name": "선반/CNC기계조작원", "sec_rate": 4.11},
    "사출": {"max_eff": 90, "job_name": "플라스틱사출기조작원", "sec_rate": 3.65},
    "소결": {"max_eff": 85, "job_name": "소성로/성형기조작원", "sec_rate": 3.71},
    "조립": {"max_eff": 90, "job_name": "부품조립원/단순노무원", "sec_rate": 3.66},
    "다이캐스팅": {"max_eff": 75, "job_name": "다이캐스트원/주조원", "sec_rate": 3.69},
    "일반구매": {"max_eff": 85, "job_name": "제조업 생산직 평균", "sec_rate": 3.98},
    "그 외": {"max_eff": 80, "job_name": "제조업 생산직 평균", "sec_rate": 3.98}
}

# ---------------------------------------------------------
# 3. 사이드바 설정 영역
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 분석 및 사정 기준 설정")

    # Secrets 등록 여부 자동 판별
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 API Key 자동 연동 완료")
    else:
        api_key = st.text_input("Gemini API Key 입력", type="password", help="구글 AI Studio API 키")

    st.divider()

    # [1] 공정 선택
    industry_list = list(INDUSTRY_CONFIG.keys())
    selected_industry = st.selectbox("공정 / 업종 선택", industry_list, index=0)
    cfg = INDUSTRY_CONFIG[selected_industry]

    # [2] 설비 효율 기준
    std_eff = st.slider(
        f"설비 효율 기준 (권장 Max: {cfg['max_eff']}%)",
        min_value=50,
        max_value=95,
        value=cfg["max_eff"],
        step=5,
        help="공정 선택 시 권장 상한 효율(Max)로 자동 세팅됩니다."
    )

    # [3] 표준 임율 기준
    st.markdown(f"**중기중앙회 공인 직종: {cfg['job_name']}**")
    std_labor_rate = st.number_input(
        "적용 임율 기준 (원/초)",
        min_value=1.0,
        max_value=15.0,
        value=cfg["sec_rate"],
        step=0.1,
        help="중소기업중앙회 임금조사 일급을 1일 8시간(28,800초)으로 나눈 초당 표준 임율입니다."
    )

    # [4] 여유율 (ET율)
    std_et_rate = st.slider(
        "여유율 / ET율 기준 (%)",
        min_value=0,
        max_value=35,
        value=10,
        step=1,
        help="양산 표준은 10%이며, 구형 기종이나 소량 다품종인 경우 15~25% 수준으로 완화할 수 있습니다."
    )

    st.divider()

    # [5] 원가 가산율 통제 기준
    st.subheader("📑 원가 가산율 통제 기준")
    std_mat_manage_rate = st.slider(
        "재료관리비율 (%)",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="순수 순재료비에 가산되는 원자재 보관/운반/수불 관리비 상한 기준 (기본 2.0%)"
    )
    std_overhead_rate = st.slider(
        "간접제조경비율 (노무비 대비 %)",
        min_value=20,
        max_value=80,
        value=50,
        step=5,
        help="통상 직접노무비의 40~50% 수준 인정"
    )
    std_admin_rate = st.slider(
        "일반관리비율 (%)",
        min_value=1.0,
        max_value=25.0,
        value=15.0,
        step=0.5,
        help="제조원가(재료비+노무비+경비) 대비 본사 관리/영업 간접비 상한 기준 (기본 15.0%)"
    )
    std_profit_rate = st.slider(
        "영업이익율 (%)",
        min_value=1.0,
        max_value=20.0,
        value=10.0,
        step=0.5,
        help="가공비(노무비+경비)+일반관리비 대비 적정 영업이익 상한 기준 (기본 10.0%, 순수 재료비 가산 배제 원칙)"
    )

    st.divider()

    # [6] 스크랩 검증 방식
    scrap_mode = st.radio("스크랩 단가 검증 방식", ["실거래가 기준 (원/kg)", "신재 대비 인정율 (%)"], index=0)
    if scrap_mode == "실거래가 기준 (원/kg)":
        target_scrap_price = st.number_input("당사 실 스크랩 매각 단가 (원/kg)", min_value=0, value=12500, step=500)
        scrap_criteria_text = f"실거래 매각단가: {target_scrap_price:,}원/kg 이상 반영 필수"
    else:
        target_scrap_ratio = st.slider("스크랩 인정 기준율 (%)", 50, 90, 65, step=5)
        scrap_criteria_text = f"신재 단가 대비 인정 기준율: {target_scrap_ratio}% 이상 반영 필수"

# ---------------------------------------------------------
# 4. 이미지 입력 영역
# ---------------------------------------------------------
st.write("### 📂 검토할 원가계산서 입력")
tab1, tab2 = st.tabs(["📋 캡처본 바로 붙여넣기 (Ctrl+V)", "📁 파일 직접 올리기"])

image_bytes = None
mime_type = "image/png"

with tab1:
    st.write("화면을 캡처(`Win + Shift + S`)한 뒤 아래 버튼을 누르세요.")
    paste_result = paste_image_button(
        label="📋 클립보드 이미지 붙여넣기",
        background_color="#1F4E79",
        hover_background_color="#2F5597",
        text_color="#FFFFFF"
    )
    if paste_result.image_data is not None:
        buf = io.BytesIO()
        paste_result.image_data.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime_type = "image/png"

with tab2:
    uploaded_file = st.file_uploader("이미지 파일 선택 (PNG, JPG)", type=["png", "jpg", "jpeg"])
    if uploaded_file is not None:
        image_bytes = uploaded_file.getvalue()
        mime_type = uploaded_file.type

# ---------------------------------------------------------
# 5. 분석 실행 및 사정 견적서 출력
# ---------------------------------------------------------
if image_bytes:
    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        st.subheader("📄 대상 원가계산서 원본")
        st.image(image_bytes, use_container_width=True)

    with col2:
        st.subheader("🔍 타당성 검토 및 당사 사정 견적")
        if not api_key:
            st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력하거나 Secrets에 등록해주세요.")
        else:
            if st.button("🚀 사정 원가계산서 자동 산출", type="primary"):
                with st.spinner("원가 요소 분석 및 표준 원가계산서 재산출 중..."):
                    client = genai.Client(api_key=api_key
