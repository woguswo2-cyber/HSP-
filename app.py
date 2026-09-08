import streamlit as st
import io
import time
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

st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 시스템")
st.caption("공정별 설비효율 Max치, 중기중앙회 공인 노임단가, 경비/이윤 마진율 기준을 대조하여 네고 포인트를 정밀 분석합니다.")

# ---------------------------------------------------------
# 2. 공정별 표준 데이터 맵 (설비효율 Max치 & 중기중앙회 공인 임율 매핑)
#    * 8시간/일 = 28,800초 기준 초당 임율 환산치
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "프레스": {
        "max_eff": 85,
        "job_name": "판금/프레스조작원",
        "sec_rate": 4.04  # 일급 약 116,368원 기준
    },
    "가공": {
        "max_eff": 90,
        "job_name": "선반/CNC기계조작원",
        "sec_rate": 4.11  # 일급 약 118,416원 기준
    },
    "사출": {
        "max_eff": 90,
        "job_name": "플라스틱사출기조작원",
        "sec_rate": 3.65  # 일급 약 105,127원 기준
    },
    "소결": {
        "max_eff": 85,
        "job_name": "소성로/성형기조작원",
        "sec_rate": 3.71  # 일급 약 106,872원 기준
    },
    "조립": {
        "max_eff": 90,
        "job_name": "부품조립원/단순노무원",
        "sec_rate": 3.66  # 일급 약 105,323원 기준
    },
    "다이캐스팅": {
        "max_eff": 75,
        "job_name": "다이캐스트원/주조원",
        "sec_rate": 3.69  # 일급 약 106,327원 기준
    },
    "일반구매": {
        "max_eff": 85,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98  # 일급 약 114,682원 기준
    },
    "그 외": {
        "max_eff": 80,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98
    }
}

# ---------------------------------------------------------
# 3. 사이드바 설정 영역
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 분석 기준 설정")
    api_key = st.text_input("Gemini API Key 입력", type="password", help="구글 AI Studio에서 발급받은 API 키")
    st.divider()

    # [1] 공정 및 업종 선택 (선택 시 효율 Max치와 임율이 기본 세팅됨)
    industry_list = list(INDUSTRY_CONFIG.keys())
    selected_industry = st.selectbox("공정 / 업종 선택", industry_list, index=0)
    cfg = INDUSTRY_CONFIG[selected_industry]

    # [2] 설비 효율 (선택한 공정의 Max 값 기준으로 즉시 뜸)
    std_eff = st.slider(
        f"설비 효율 기준 (권장 Max: {cfg['max_eff']}%)",
        min_value=50,
        max_value=95,
        value=cfg["max_eff"],
        step=5,
        help="공정 선택 시 추천 상한 효율(Max)로 자동 세팅됩니다."
    )

    # [3] 표준 임율 (중소기업중앙회 공인 통계치 연동)
    st.markdown(f"**중기중앙회 공인 임율: {cfg['job_name']}**")
    std_labor_rate = st.number_input(
        "적용 임율 기준 (원/초)",
        min_value=1.0,
        max_value=15.0,
        value=cfg["sec_rate"],
        step=0.1,
        help="중소기업중앙회 임금조사 일급을 1일 8시간(28,800초)으로 나눈 초당 표준 임율입니다."
    )

    # [4] 여유율 (ET율)
    std_et_rate = st.slider("여유율 / ET율 기준 (%)", 0, 35, 10, step=1)

    st.divider()

    # [5] 경비율 / 관리비 / 이윤 조절 섹션
    st.subheader("📑 원가 가산율 통제 기준")
    std_overhead_rate = st.slider("간접제조경비율 (노무비 대비 %)", 20, 80, 50, step=5, help="통상 직접노무비의 40~50% 수준")
    std_admin_rate = st.slider("일반관리비율 (%)", 1.0, 15.0, 5.0, step=0.5, help="제조원가의 5% 수준 인정")
    std_profit_rate = st.slider("영업이윤율 (%)", 1.0, 15.0, 6.0, step=0.5, help="가공비(노무비+경비)+일반관리비의 5~7% 인정 (재료비 제외)")
    std_mfg_manage_rate = st.slider("제조관리비율 (%)", 0.0, 10.0, 2.0, step=0.5, help="포장/출하 등 별도 제조관리비 인정 상한")

    st.divider()

    # [6] 스크랩 검증 방식
    scrap_mode = st.radio("스크랩 단가 검증 방식", ["실거래가 기준 (원/kg)", "신재 대비 인정율 (%)"], index=0)
    if scrap_mode == "실거래가 기준 (원/kg)":
        target_scrap_price = st.number_input("당사 실 스크랩 매각 단가 (원/kg)", min_value=0, value=12500, step=500)
        scrap_criteria_text = f"당사 실거래 매각단가: {target_scrap_price:,}원/kg 이상 반영 필수"
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
# 5. 분석 실행 및 결과 출력
# ---------------------------------------------------------
if image_bytes:
    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        st.subheader("📄 대상 원가계산서")
        st.image(image_bytes, use_container_width=True)

    with col2:
        st.subheader("🔍 타당성 검토 결과")
        if not api_key:
            st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력해주세요.")
        else:
            if st.button("🚀 견적 타당성 분석 실행", type="primary"):
                with st.spinner("원가계산서 항목별 정밀 심사 중... (503 지연 시 자동 재시도)"):
                    client = genai.Client(api_key=api_key)

                    prompt = f"""
                    당신은 제조 및 자동차 부품 구매팀의 원가 분석 수석관입니다.
                    첨부된 협력사의 원가계산서 이미지를 정밀 분석하여 아래의 '내부 통제 기준'과 대조하고 네고 리포트를 작성하세요.

                    [내부 원가 통제 기준]
                    1. 적용 공정/업종: {selected_industry}
                    2. 기준 설비 효율: {std_eff}% 이상 필수 (원가계산서 기재 효율이 이보다 낮으면 생산성 미달 전가로 삭감 지적)
                    3. 기준 초당 임율: {std_labor_rate} 원/초 (중소기업중앙회 공인 노임단가 기준치 초과 여부 집중 검증)
                    4. 여유율 (ET율): 기준 {std_et_rate}% (이를 초과하여 여유시간/준비시간을 잡았는지 확인)
                    5. 경비 및 이윤 통제 기준:
                       - 간접제조경비율: 노무비의 {std_overhead_rate}% 이하
                       - 제조관리비율: {std_mfg_manage_rate}% 이하
                       - 일반관리비율: {std_admin_rate}% 이하
                       - 영업이윤율: {std_profit_rate}% 이하 (순수 재료비에 이윤을 가산했는지 적발 필수)
                    6. 스크랩 단가: {scrap_criteria_text}

                    [출력 서식]
                    ### 1. 기본 견적 정보 요약
                    - 협력사명 / 차종 / 품명 / 품번 / 적용 재질 / 견적 제출일
                    - 협력사 제출 총 제조원가 및 최종 견적가

                    ### 2. 종합 판정 결과
                    - 🔴 [재협상 강력 권고] / 🟡 [주의 / 소명 요구] / 🟢 [원안 적합] 중 택1

                    ### 3. 세부 과다 계상 항목 및 네고 가능 금액 산출
                    - 설비 효율 정상화({std_eff}%) 및 임율({std_labor_rate}원/초) 적용 시 노무비 절감 가능액
                    - 스크랩 환입 단가 축소 여부 및 정상화 시 재료비 절감액
                    - 경비율, 일반관리비({std_admin_rate}%), 이윤율({std_profit_rate}%) 초과 계상액
                    - 수작업(Hand work) 및 불필요 공수 소명 대상 지적

                    ### 4. 협력사 송부용 공식 네고 코멘트
                    - 구매팀 명의로 즉시 발송 가능한 객관적/논리적 요구 문구 (항목별 수치 근거 제시)
                    """

                    # 503 서버 과부하 자동 재시도 로직
                    success = False
                    for attempt in range(3):
                        try:
                            response = client.models.generate_content(
                                model="gemini-3.6-flash",
                                contents=[
                                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                                    prompt
                                ]
                            )
                            st.success("타당성 검토 완료!")
                            st.markdown(response.text)
                            success = True
                            break
                        except Exception as e:
                            if "503" in str(e) and attempt < 2:
                                time.sleep(3)
                                continue
                            else:
                                st.error(f"오류 발생: {e}")
                                break
