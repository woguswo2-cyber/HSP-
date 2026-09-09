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
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="구매 견적/원가계산서 타당성 자동 검토",
    page_icon="📊",
    layout="wide"
)

st.title("📊 협력사 견적/원가계산서 타당성 자동 분석 및 사정 견적 산출")
st.caption("공정별 설비효율, 기계경비 현실화 배부율, 중기중앙회 공인 임율을 반영하여 신뢰도 높은 '적정 사정 원가계산서'를 자동 생성합니다.")

# ---------------------------------------------------------
# 2. 공정별 표준 데이터 맵 (기계경비 배부율 현실화 반영)
#    - 장치산업(프레스/다이캐스팅/가공/사출/소결): 180% ~ 250%
#    - 노동집약(조립): 50%
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "프레스": {
        "max_eff": 85,
        "job_name": "판금/프레스조작원",
        "sec_rate": 4.04,
        "overhead_rate": 220,  # 300T 고속 프레스 설비상각/전력비 반영
        "desc": "고가 프레스 설비 상각 및 동력비가 큰 장치 공정 (기본 220%)"
    },
    "가공": {
        "max_eff": 90,
        "job_name": "선반/CNC기계조작원",
        "sec_rate": 4.11,
        "overhead_rate": 200,  # MCT/CNC 머시닝 상각/절삭유/툴링비
        "desc": "정밀 공작기계 상각 및 절삭유/공구비 반영 (기본 200%)"
    },
    "사출": {
        "max_eff": 90,
        "job_name": "플라스틱사출기조작원",
        "sec_rate": 3.65,
        "overhead_rate": 200,  # 사출기 히터 전력비/로봇 상각비
        "desc": "사출 성형기 히터 전력비 및 취출 로봇 상각비 반영 (기본 200%)"
    },
    "소결": {
        "max_eff": 85,
        "job_name": "소성로/성형기조작원",
        "sec_rate": 3.71,
        "overhead_rate": 200,  # 성형프레스/연속 소결로 가스/전력비
        "desc": "분말성형 프레스 및 연속 소결로 분위기가스/전력비 반영 (기본 200%)"
    },
    "다이캐스팅": {
        "max_eff": 75,
        "job_name": "다이캐스트원/주조원",
        "sec_rate": 3.69,
        "overhead_rate": 250,  # 용해로 가스/전기세, 대형 주조기 상각
        "desc": "용해로 가스·전력비 및 고온 주조 설비 감가상각 반영 (기본 250%)"
    },
    "조립": {
        "max_eff": 90,
        "job_name": "부품조립원/단순노무원",
        "sec_rate": 3.66,
        "overhead_rate": 50,   # 단순 작업 라인 소모품/소형치구
        "desc": "작업자 중심 노동집약 공정, 치구/소모품 위주 (기본 50%)"
    },
    "일반구매": {
        "max_eff": 85,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98,
        "overhead_rate": 100,
        "desc": "범용 외주 임가공/구매 부품 표준선 (기본 100%)"
    },
    "그 외": {
        "max_eff": 80,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98,
        "overhead_rate": 100,
        "desc": "기타 가공/조립 표준선 (기본 100%)"
    }
}

# ---------------------------------------------------------
# 3. 사이드바 설정 영역
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 분석 및 사정 기준 설정")

    # Secrets 등록 여부 자동 확인
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 API Key 자동 연동 완료")
    else:
        api_key = st.text_input("Gemini API Key 입력", type="password", help="구글 AI Studio API 키")

    st.divider()

    # [1] 공정 선택 (선택 시 효율, 임율, 현실화 경비율이 한꺼번에 바뀜)
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
        help="중기중앙회 임금조사 1일 8시간(28,800초) 기준 초당 임율"
    )

    # [4] 여유율 (ET율)
    std_et_rate = st.slider(
        "여유율 / ET율 기준 (%)",
        min_value=0,
        max_value=35,
        value=10,
        step=1,
        help="양산 표준은 10%이며, 구형 기종이나 소량 다품종은 15~25% 수준 인정"
    )

    st.divider()

    # [5] 원가 가산율 통제 기준 (업종별 현실화 간접경비율 탑재)
    st.subheader("📑 원가 가산율 통제 기준")
    
    std_mat_manage_rate = st.slider(
        "재료관리비율 (%)",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="순재료비의 2.0% 기준 (입고운반비/보관비 중복 배제 필수)"
    )

    # 업종별 현실화된 기본값 자동 반영
    std_overhead_rate = st.slider(
        f"간접제조경비율 (노무비 대비 %)",
        min_value=20,
        max_value=350,
        value=cfg["overhead_rate"],
        step=10,
        help=cfg["desc"]
    )
    st.caption(f"ℹ️ {cfg['desc']}")

    std_admin_rate = st.slider(
        "일반관리비율 (%)",
        min_value=1.0,
        max_value=25.0,
        value=15.0,
        step=0.5,
        help="제조원가(재료비+노무비+경비) 대비 본사 관리비 (기본 15.0%)"
    )

    std_profit_rate = st.slider(
        "영업이익율 (%)",
        min_value=1.0,
        max_value=20.0,
        value=10.0,
        step=0.5,
        help="가공비(노무비+경비)+일반관리비 대비 영업이익 (기본 10.0%, 순재료비 이윤 배제)"
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
    st.write("화면을 캡처한 뒤 아래 버튼을 누르세요.")
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
                spin_msg = "업종별 기계경비 현실화 및 표준 사정 원가계산서 재산출 중..."
                with st.spinner(spin_msg):
                    client = genai.Client(api_key=api_key)

                    prompt_parts = [
                        "당신은 자동차 부품 및 정밀제조업 구매팀의 원가 분석 수석관입니다.",
                        "제출된 원가계산서 이미지를 정밀 판독하여 과다 계상분을 삭감하고, 공정 특성을 반영한 당사 표준 기준에 맞추어 '정상 사정 원가계산서'를 재계산하세요.",
                        "",
                        "[당사 사정 원가 통제 기준]",
                        f"1. 적용 공정: {selected_industry} (특성: {cfg['desc']})",
                        f"2. 기준 설비 효율: {std_eff}% 이상 필수 (원가서 기재 효율 미달 시 생산성 저하 전가로 삭감)",
                        f"3. 적용 임율 기준: {std_labor_rate} 원/초 (중소기업중앙회 공인 노임단가 초과분 삭감)",
                        f"4. 여유율(ET율): 기준 {std_et_rate}% (초과 반영된 비효율 준비시간 배제)",
                        f"5. 재료관리비율: 순재료비의 {std_mat_manage_rate}% 이하 (입고운반비 중복 반영 엄격 배제)",
                        f"6. 간접제조경비(기계경비): 노무비의 {std_overhead_rate}% 적용",
                        "   - 핵심 지침: 프레스/사출/가공/다이캐스팅/소결 등 고가 장치 설비는 감가상각과 동력비가 발생하므로 일률적 50% 삭감을 금지하고, 업종별 현실화된 장치경비율 및 설비효율({std_eff}%) 정상화에 따른 비례 삭감 적용",
                        "   - 만약 제출된 기계경비가 과다한 경우 '설비 감가상각 내용연수(5년) 경과 여부 소명'을 공식 지적할 것",
                        f"7. 일반관리비율: 제조원가의 {std_admin_rate}% 이하",
                        f"8. 영업이익율: (가공비+일반관리비)의 {std_profit_rate}% 이하 (순재료비에 이윤 가산 엄격 배제)",
                        f"9. 스크랩 단가 검증: {scrap_criteria_text}",
                        "",
                        "[출력 규칙]",
                        "반드시 첫 부분에 START_JSON 과 END_JSON 태그 사이에 아래 구조의 순수 JSON 데이터만 넣으세요.",
                        "모든 금액 및 비율 수치는 쉼표(,) 없는 순수 숫자여야 합니다.",
                        "START_JSON",
                        json.dumps({
                            "item_info": {"supplier": "협력사명", "part_name": "품명", "part_no": "품번"},
                            "comparison": {"submitted_price": 0.0, "adjusted_price": 0.0, "cost_reduction": 0.0, "reduction_rate": 0.0},
                            "cost_breakdown": [
                                {"category": "1. 재료비", "item": "투입재료비", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""},
                                {"category": "1. 재료비", "item": "스크랩환입(-)", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""},
                                {"category": "1. 재료비", "item": "순재료비", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""},
                                {"category": "1. 재료비", "item": "재료관리비", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": f"{std_mat_manage_rate}% 적용(운반비 중복 배제)"},
                                {"category": "2. 가공비", "item": "직접노무비", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": f"임율 {std_labor_rate}원/초, 효율 {std_eff}%"},
                                {"category": "2. 가공비", "item": "간접제조경비", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": f"장치경비율 {std_overhead_rate}% 적용"},
                                {"category": "3. 제조원가", "item": "제조원가 합계", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": ""},
                                {"category": "4. 일반관리비", "item": "일반관리비", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": f"{std_admin_rate}% 적용"},
                                {"category": "5. 영업이익", "item": "영업이익", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": f"{std_profit_rate}% 적용"},
                                {"category": "6. 최종단가", "item": "최종 견적 단가", "submitted": 0.0, "adjusted": 0.0, "diff": 0.0, "note": "당사 사정 목표가"}
                            ]
                        }, ensure_ascii=False),
                        "END_JSON",
                        "",
                        "END_JSON 이후에는 구체적 사정 논리와 협력사 통보용 공식 공문 문구를 마크다운으로 작성하세요. (기계경비와 관련하여 설비 감가상각 완료 여부 소명 요청 문구 포함)"
                    ]
                    prompt = "\n".join(prompt_parts)

                    for attempt in range(3):
                        try:
                            response = client.models.generate_content(
                                model="gemini-3.6-flash",
                                contents=[
                                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                                    prompt
                                ]
                            )
                            res_text = response.text

                            if "START_JSON" in res_text and "END_JSON" in res_text:
                                raw_json = res_text.split("START_JSON")[1].split("END_JSON")[0].strip()
                                raw_json = re.sub(r"^```json\s*", "", raw_json)
                                raw_json = re.sub(r"^```\s*", "", raw_json)
                                raw_json = re.sub(r"\s*```$", "", raw_json)
                                
                                data = json.loads(raw_json)

                                # 상단 요약 카드
                                comp = data["comparison"]
                                c_sub, c_adj, c_diff, c_rate = st.columns(4)
                                c_sub.metric("협력사 제출가", f"{comp['submitted_price']:,.1f}원")
                                c_adj.metric("당사 사정 목표가", f"{comp['adjusted_price']:,.1f}원")
                                c_diff.metric("절감 가능액", f"-{comp['cost_reduction']:,.1f}원")
                                c_rate.metric("절감율", f"-{comp['reduction_rate']:.1f}%")

                                # 표준 원가계산서 대조 테이블
                                st.markdown("#### 📋 표준 견적 대조 원가계산서")
                                df = pd.DataFrame(data["cost_breakdown"])
                                df.columns = ["구분", "항목", "협력사 제출", "당사 사정가", "차액(절감)", "사정 기준 및 사유"]
                                st.dataframe(df, use_container_width=True, hide_index=True)

                                # CSV 다운로드 (영문 파일명으로 인코딩 에러 방지)
                                csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                                st.download_button(
                                    label="📥 사정 원가계산서 엑셀(CSV) 다운로드",
                                    data=csv_data,
                                    file_name="Cost_Audit_Report.csv",
                                    mime="text/csv"
                                )
                                st.divider()

                                comment_text = res_text.split("END_JSON")[1].strip()
                                st.markdown(comment_text)
                            else:
                                st.markdown(res_text)

                            break
                        except Exception as e:
                            if "503" in str(e) and attempt < 2:
                                time.sleep(3)
                                continue
                            else:
                                st.error(f"오류 발생: {e}")
                                break
