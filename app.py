import streamlit as st
import io
from google import genai
from google.genai import types
from streamlit_paste_button import paste_image_button

# 1. 페이지 레이아웃
st.set_page_config(
    page_title="구매 견적/원가계산서 타당성 자동 검토",
    page_icon="📊",
    layout="wide"
)

st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 시스템")
st.caption("캡처본(Ctrl+V)을 바로 붙여넣거나 파일을 올려 실시간 네고 포인트를 도출합니다.")

# 2. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 분석 기준 설정")
    api_key = st.text_input("Gemini API Key 입력", type="password", help="발급받은 API 키를 입력하세요.")
    st.divider()
    std_press_eff = st.slider("표준 프레스 가동효율 기준 (%)", 50, 95, 80, step=5)
    std_scrap_ratio = st.slider("스크랩 매각가 인정 기준 (%)", 50, 90, 65, step=5)

# 3. 이미지 입력 (파일 업로드 OR 클립보드 붙여넣기)
st.write("### 📂 이미지 입력 방식 선택")
tab1, tab2 = st.tabs(["📋 캡처본 바로 붙여넣기 (Ctrl+V)", "📁 파일 직접 올리기 (드래그앤드롭)"])

image_bytes = None
mime_type = "image/png"

with tab1:
    st.write("화면을 캡처(`Win + Shift + S`)한 뒤 아래 버튼을 클릭하세요.")
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
    uploaded_file = st.file_uploader("검토할 이미지 파일 선택 (PNG, JPG)", type=["png", "jpg", "jpeg"])
    if uploaded_file is not None:
        image_bytes = uploaded_file.getvalue()
        mime_type = uploaded_file.type

# 4. 분석 결과 출력 영역
if image_bytes:
    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        st.subheader("📄 검토 대상 원가계산서")
        st.image(image_bytes, use_container_width=True)

    with col2:
        st.subheader("🔍 AI 타당성 정밀 검토 결과")
        if not api_key:
            st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력해주세요.")
        else:
            if st.button("🚀 견적 타당성 분석 실행", type="primary"):
                with st.spinner("원가계산서 정밀 판정 중..."):
                    try:
                        client = genai.Client(api_key=api_key)

                        prompt = f"""
                        당신은 자동차/전자부품 구매팀 원가분석 전문가입니다.
                        제공된 원가계산서 이미지를 분석하여 구매 담당자가 협력사와 네고할 수 있는 타당성 검토 리포트를 작성하세요.

                        [내부 검토 기준]
                        1. 설비/프레스 가동효율: {std_press_eff}% 이상 인정 (미달 시 노무비 과다로 지적)
                        2. 스크랩 단가 인정률: 신재 단가 대비 {std_scrap_ratio}% 수준 반영 필수
                        3. 수작업(Hand Work) 공정: 대량 양산 자동화 라인 대체 가능 여부 소명 대상

                        [출력 서식]
                        1. 기본 견적 정보 요약 (업체명, 차종, 품명, 품번, 적용 재질)
                        2. 종합 판정 결과 (🔴 재협상 필요 / 🟡 주의 / 🟢 적합)
                        3. 세부 과다 계상 지적 사항 (가동효율, 스크랩 단가, 불필요 수작업 공수)
                        4. 협력사 전달용 공식 코멘트 문구
                        """

                        response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        prompt
    ]
)
                        st.success("분석 완료!")
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
