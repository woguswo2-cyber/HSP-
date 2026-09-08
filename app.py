import streamlit as st
from google import genai
from google.genai import types

# 1. 페이지 레이아웃
st.set_page_config(
    page_title="구매 견적/원가계산서 타당성 자동 검토",
    page_icon="📊",
    layout="wide"
)

st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 시스템")
st.caption("원가계산서 캡처 사진이나 스캔본을 올리면 비전 모델이 비효율 공정과 네고 포인트를 도출합니다.")

# 2. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 분석 기준 설정")
    api_key = st.text_input("Gemini API Key 입력", type="password", help="AI Studio에서 발급받은 API 키를 넣으세요.")
    st.divider()
    std_press_eff = st.slider("표준 프레스 가동효율 기준 (%)", 50, 95, 80, step=5)
    std_scrap_ratio = st.slider("스크랩 매각가 인정 기준 (%)", 50, 90, 65, step=5)

# 3. 이미지 업로드 및 검토 영역
uploaded_file = st.file_uploader("📂 검토할 원가계산서/견적서 이미지 (PNG, JPG)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    col1, col2 = st.columns([1, 1], gap="medium")
    
    with col1:
        st.subheader("📄 업로드된 원가계산서")
        st.image(uploaded_file, use_container_width=True)
        
    with col2:
        st.subheader("🔍 AI 타당성 정밀 검토 결과")
        if not api_key:
            st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력해주세요.")
        else:
            if st.button("🚀 견적 타당성 분석 실행", type="primary"):
                with st.spinner("원가계산서 정밀 판정 중..."):
                    try:
                        client = genai.Client(api_key=api_key)
                        img_bytes = uploaded_file.getvalue()
                        mime_type = uploaded_file.type

                        prompt = f"""
                        당신은 자동차/전자부품 구매팀 원가분석 전문가입니다.
                        제공된 원가계산서 이미지를 분석하여 구매 담당자가 협력사와 네고할 수 있는 타당성 검토 리포트를 작성하세요.

                        [내부 검토 기준]
                        1. 설비/프레스 가동효율: {std_press_eff}% 이상 인정 (미달 시 노무비 과다로 지적)
                        2. 스크랩 단가 인정률: 신재 단가 대비 {std_scrap_ratio}% 수준 반영 필수
                        3. 수작업(Hand Work) 공정: 대량 양산 자동화 라인 대체 가능 여부 소명 대상

                        [출력 서식]
                        1. 기본 견적 정보 요약 (업체명, 차종, 품명, 품번, 재질, 제출 제조원가, 최종 견적가)
                        2. 종합 판정 결과 (🔴 재협상 필요 / 🟡 주의 / 🟢 적합)
                        3. 세부 과다 계상 지적 사항 (효율 저하에 따른 노무비 부풀림, 스크랩 단가 축소, 불필요 공수)
                        4. 협력사 전달용 공식 코멘트 문구
                        """

                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[
                                types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
                                prompt
                            ]
                        )
                        st.success("분석 완료!")
                        st.markdown(response.text)
                    except Exception as e:
                        st.error(f"오류 발생: {e}")
