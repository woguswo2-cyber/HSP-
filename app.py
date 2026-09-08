import streamlit as st
import io
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

st.set_page_config(
    page_title="구매 견적/원가계산서 타당성 자동 검토",
    page_icon="📊",
    layout="wide"
)

st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 시스템")
st.caption("업종별 설비 효율, 여유율(ET율), 실거래 스크랩 시세를 대조하여 과다 계상 및 네고 포인트를 정밀 분석합니다.")

# ---------------------------------------------------------
# 사이드바 설정
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 분석 기준 설정")
    api_key = st.text_input("Gemini API Key 입력", type="password", help="구글 AI Studio API 키")
    st.divider()

    # 1. 업종 선택
    industry_list = ["프레스", "가공", "사출", "소결", "조립", "다이캐스팅", "일반구매", "그 외"]
    selected_industry = st.selectbox("공정 / 업종 구분", industry_list, index=0)

    # 업종별 표준 효율 기본값 매핑
    industry_default_eff = {
        "프레스": 80,
        "가공": 85,
        "사출": 85,
        "소결": 80,
        "조립": 90,
        "다이캐스팅": 75,
        "일반구매": 80,
        "그 외": 80
    }

    # 2. 설비 효율
    std_eff = st.slider(
        "설비 효율 기준 (%)",
        min_value=50,
        max_value=95,
        value=industry_default_eff[selected_industry],
        step=5,
        help="선택한 업종의 표준 공정 가동효율 기준입니다."
    )

    # 3. 여유율 (ET율) 설정 추가
    std_et_rate = st.slider(
        "여유율 / ET율 기준 (%)",
        min_value=0,
        max_value=35,
        value=10,
        step=1,
        help="양산 표준은 통상 10%이며, 구형 기종이나 소량 다품종인 경우 15~25% 수준으로 완화할 수 있습니다."
    )

    st.divider()

    # 4. 스크랩 단가 검토 기준
    scrap_mode = st.radio(
        "스크랩 단가 검증 방식",
        ["실거래가 기준 (원/kg)", "신재 대비 인정율 (%)"],
        index=0
    )

    if scrap_mode == "실거래가 기준 (원/kg)":
        target_scrap_price = st.number_input(
            "당사 실 스크랩 매각 단가 (원/kg)",
            min_value=0,
            value=12500,
            step=500,
            help="사내에서 실제 거래/매각 중인 고철, 황동, 알루미늄 등의 kg당 단가를 입력하세요."
        )
        scrap_criteria_text = f"실거래 매각 단가 기준: {target_scrap_price:,}원/kg 이상 반영 필수 (미달 시 재료비 과다로 지적)"
    else:
        target_scrap_ratio = st.slider("스크랩 인정 기준율 (%)", 50, 90, 65, step=5)
        scrap_criteria_text = f"신재 단가 대비 인정 기준율: {target_scrap_ratio}% 이상 반영 필수"

# ---------------------------------------------------------
# 이미지 업로드 & 붙여넣기
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
# 분석 실행 및 결과 출력
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
                with st.spinner("업종 기준, 여유율(ET율), 스크랩 단가 종합 대조 중..."):
                    try:
                        client = genai.Client(api_key=api_key)

                        prompt = f"""
                        당신은 자동차/제조 부품 구매팀의 원가 전문 분석관입니다.
                        제출된 원가계산서 이미지를 분석하고 다음 기준을 대조하여 단가 네고 리포트를 작성하세요.

                        [적용 검토 기준]
                        - 적용 공정/업종: {selected_industry}
                        - 기준 설비 효율: {std_eff}% 이상 (원가계산서의 효율이 이보다 낮으면 생산성 저하 전가로 지적)
                        - 기준 여유율 (ET율): {std_et_rate}% (협력사가 책정한 여유율/준비시간 등이 이 기준을 초과하면 과다 산정으로 지적)
                        - 스크랩 검증 기준: {scrap_criteria_text}
                        - 수작업(Hand Work) 공정: 대량 양산 자동화 라인 대체 가능 여부 소명 대상

                        [출력 서식]
                        1. 기본 견적 요약 (협력사명, 차종, 품명, 품번, 재질, 제출 제조원가, 최종 견적가)
                        2. 종합 판정 결과 (🔴 [재협상 강력 권고] / 🟡 [주의 / 소명 필요] / 🟢 [적합])
                        3. 핵심 네고 포인트 (구체적 계산 수치 제시)
                           - 설비 효율 정상화({std_eff}%) 적용 시 노무비 절감 가능액
                           - 여유율(ET율) 적용 적정성 검토 (기준 {std_et_rate}% 대비 차이 분석)
                           - 스크랩 환입 단가 정상 반영 시 재료비 절감 가능액
                           - 수작업/부대비용 과다 여부
                        4. 협력사 전달용 공식 공문/메일 문구
                        """

                        response = client.models.generate_content(
                            model="gemini-3.6-flash",
                            contents=[
                                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                                prompt
                            ]
                        )
                        st.success("분석 완료!")
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
