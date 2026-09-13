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
st.caption("견적서 갑지(총괄)와 을지(세부내역) 등 복수 이미지를 교차 검증하여 표준 사정 원가계산서를 도출합니다.")

# ---------------------------------------------------------
# 2. 공정별 표준 데이터 맵
# ---------------------------------------------------------
INDUSTRY_CONFIG = {
    "프레스": {
        "max_eff": 85,
        "job_name": "판금/프레스조작원",
        "sec_rate": 4.04,
        "overhead_rate": 220,
        "desc": "고가 프레스 설비 상각 및 동력비가 큰 장치 공정 (상한 220%)"
    },
    "가공": {
        "max_eff": 90,
        "job_name": "선반/CNC기계조작원",
        "sec_rate": 4.11,
        "overhead_rate": 200,
        "desc": "정밀 공작기계 상각 및 절삭유/공구비 반영 (상한 200%)"
    },
    "사출": {
        "max_eff": 90,
        "job_name": "플라스틱사출기조작원",
        "sec_rate": 3.65,
        "overhead_rate": 200,
        "desc": "사출 성형기 히터 전력비 및 취출 로봇 상각비 반영 (상한 200%)"
    },
    "소결": {
        "max_eff": 85,
        "job_name": "소성로/성형기조작원",
        "sec_rate": 3.71,
        "overhead_rate": 200,
        "desc": "분말성형 프레스 및 연속 소결로 분위기가스/전력비 반영 (상한 200%)"
    },
    "다이캐스팅": {
        "max_eff": 75,
        "job_name": "다이캐스트원/주조원",
        "sec_rate": 3.69,
        "overhead_rate": 250,
        "desc": "용해로 가스·전력비 및 고온 주조 설비 감가상각 반영 (상한 250%)"
    },
    "조립": {
        "max_eff": 90,
        "job_name": "부품조립원/단순노무원",
        "sec_rate": 3.66,
        "overhead_rate": 50,
        "desc": "작업자 중심 노동집약 공정, 치구/소모품 위주 (상한 50%)"
    },
    "일반구매": {
        "max_eff": 85,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98,
        "overhead_rate": 100,
        "desc": "범용 외주 임가공/구매 부품 표준선 (상한 100%)"
    },
    "그 외": {
        "max_eff": 80,
        "job_name": "제조업 생산직 평균",
        "sec_rate": 3.98,
        "overhead_rate": 100,
        "desc": "기타 가공/조립 표준선 (상한 100%)"
    }
}

# ---------------------------------------------------------
# 3. 사이드바 설정 영역
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 분석 및 사정 기준 설정")

    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 API Key 자동 연동 완료")
    else:
        api_key = st.text_input("Gemini API Key 입력", type="password", help="구글 AI Studio API 키")

    st.divider()

    industry_list = list(INDUSTRY_CONFIG.keys())
    selected_industry = st.selectbox("공정 / 업종 선택", industry_list, index=0)
    cfg = INDUSTRY_CONFIG[selected_industry]

    std_eff = st.slider(
        f"설비 효율 기준 (권장 Max: {cfg['max_eff']}%)",
        min_value=50,
        max_value=95,
        value=cfg["max_eff"],
        step=5
    )

    st.markdown(f"**중기중앙회 공인 직종: {cfg['job_name']}**")
    std_labor_rate = st.number_input(
        "적용 임율 기준 (원/초)",
        min_value=1.0,
        max_value=15.0,
        value=cfg["sec_rate"],
        step=0.1,
        help="중기중앙회 통계 1일 8시간(28,800초) 기준 초당 임율"
    )

    std_et_rate = st.slider(
        "여유율 / ET율 기준 (%)",
        min_value=0,
        max_value=35,
        value=10,
        step=1
    )

    st.divider()
    st.subheader("📑 원가 가산율 통제 기준 (상한선)")

    std_mat_manage_rate = st.slider(
        "재료관리비율 상한 (%)",
        min_value=0.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        help="순재료비의 2.0% 기준 (입고운반비/보관비 중복 배제 필수)"
    )

    std_overhead_rate = st.slider(
        "간접제조경비율 상한 (노무비 대비 %)",
        min_value=20,
        max_value=350,
        value=cfg["overhead_rate"],
        step=10,
        help=cfg["desc"]
    )
    st.caption(f"ℹ️ {cfg['desc']}")

    std_admin_rate = st.slider(
        "일반관리비율 상한 (%)",
        min_value=1.0,
        max_value=25.0,
        value=15.0,
        step=0.5
    )

    std_profit_rate = st.slider(
        "영업이익율 상한 (%)",
        min_value=1.0,
        max_value=20.0,
        value=10.0,
        step=0.5
    )

    st.divider()
    scrap_mode = st.radio("스크랩 단가 검증 방식", ["실거래가 기준 (원/kg)", "신재 대비 인정율 (%)"], index=0)
    if scrap_mode == "실거래가 기준 (원/kg)":
        target_scrap_price = st.number_input("당사 실 스크랩 매각 단가 (원/kg)", min_value=0, value=12500, step=500)
        scrap_criteria_text = f"실거래 매각단가: {target_scrap_price:,}원/kg 이상 반영 (재활용/매각 가능 소재에 한함)"
    else:
        target_scrap_ratio = st.slider("스크랩 인정 기준율 (%)", 50, 90, 65, step=5)
        scrap_criteria_text = f"신재 단가 대비 인정 기준율: {target_scrap_ratio}% 이상 반영 (재활용/매각 가능 소재에 한함)"

# ---------------------------------------------------------
# 4. 복수 이미지 입력 영역 (갑지, 을지 등)
# ---------------------------------------------------------
if "clipboard_images" not in st.session_state:
    st.session_state.clipboard_images = []

st.write("### 📂 검토할 원가계산서 입력 (갑지, 을지 등 여러 장 업로드 가능)")
tab1, tab2 = st.tabs(["📋 캡처본 연속 붙여넣기 (Ctrl+V)", "📁 파일 여러 장 선택 올리기"])

image_list = []

with tab1:
    col_btn, col_clear = st.columns([2, 1])
    with col_btn:
        paste_result = paste_image_button(
            label="📋 현재 캡처본 추가하기",
            background_color="#1F4E79",
            hover_background_color="#2F5597",
            text_color="#FFFFFF"
        )
    with col_clear:
        if st.button("🗑️ 붙여넣은 이미지 초기화"):
            st.session_state.clipboard_images = []
            st.rerun()

    if paste_result.image_data is not None:
        buf = io.BytesIO()
        paste_result.image_data.save(buf, format="PNG")
        new_bytes = buf.getvalue()
        if not st.session_state.clipboard_images or st.session_state.clipboard_images[-1]["bytes"] != new_bytes:
            st.session_state.clipboard_images.append({
                "bytes": new_bytes,
                "mime": "image/png"
            })

    if st.session_state.clipboard_images:
        image_list = st.session_state.clipboard_images
        st.info(f"현재 총 {len(image_list)}장의 캡처 이미지가 등록되었습니다.")

with tab2:
    uploaded_files = st.file_uploader(
        "견적서 파일 선택 (갑지, 을지 등 여러 파일 동시 선택 가능)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    if uploaded_files:
        image_list = [{"bytes": f.getvalue(), "mime": f.type} for f in uploaded_files]

# ---------------------------------------------------------
# 5. 분석 실행 및 사정 견적서 출력
# ---------------------------------------------------------
if image_list:
    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        st.subheader(f"📄 대상 견적서 원본 (총 {len(image_list)}장)")
        for idx, img_item in enumerate(image_list):
            st.image(img_item["bytes"], caption=f"페이지 {idx + 1}", use_container_width=True)

    with col2:
        st.subheader("🔍 타당성 검토 및 당사 사정 견적")
        if not api_key:
            st.warning("👈 왼쪽 사이드바에 Gemini API Key를 입력하거나 Secrets에 등록해주세요.")
        else:
            if st.button("🚀 사정 원가계산서 자동 산출", type="primary"):
                spin_msg = f"총 {len(image_list)}장의 견적서(갑지/을지) 교차 검증 및 사정 원가계산서 생성 중..."
                with st.spinner(spin_msg):
                    client = genai.Client(api_key=api_key)

                    # 복수 이미지를 API 파트로 구성
                    contents = []
                    for img_item in image_list:
                        contents.append(types.Part.from_bytes(data=img_item["bytes"], mime_type=img_item["mime"]))

                    prompt = f"""
                    당신은 자동차 부품 및 정밀제조업 구매팀의 원가 분석 수석관입니다.
                    제공된 복수의 원가계산서 이미지(갑지-총괄 요약표, 을지-공정/재료 세부명세 등)를 종합 대조하여 과다 계상분을 삭감하고 '정상 사정 원가계산서'를 재계산하세요.

                    [갑지/을지 교차 분석 핵심 지침]
                    1. 을지(세부내역)의 투입단중, C/T, 임율, 기계경비, 스크랩 환입을 정밀 검증하여 적정 제조원가를 도출하세요.
                    2. 을지의 합계 금액과 갑지(총괄표)의 재료비, 가공비, 일반관리비, 이윤이 일치하는지 대조하고 중복 계상(운반비, 관리비 등)을 적발하세요.

                    [당사 사정 원가 통제 기준]
                    1. 적용 공정: {selected_industry} (특성: {cfg['desc']})
                    2. 기준 설비 효율: {std_eff}% 이상 필수 (원가서 기재 효율 미달 시 삭감)
                    3. 적용 임율 기준: {std_labor_rate} 원/초 (중기중앙회 공인 노임단가 초과분 삭감, 단 협력사가 더 낮은 임율을 적었다면 협력사 값 유지)
                    4. 여유율(ET율): 기준 {std_et_rate}% (초과 반영된 준비시간 배제)
                    5. 재료관리비율: 순재료비의 {std_mat_manage_rate}% 이하 (입고운반비/보관비 중복 반영 엄격 배제)
                    6. 간접제조경비율: 당사 상한 기준은 {std_overhead_rate}%이나, 협력사 제출 비율이 더 낮다면 협력사 제출치 유지.
                    7. 일반관리비율: 당사 상한 기준 {std_admin_rate}%와 협력사 제출 비율 중 낮은 비율(Min) 적용.
                    8. 영업이익율: 당사 상한 기준 {std_profit_rate}%와 협력사 제출 비율 중 낮은 비율(Min) 적용 (순재료비 이윤 배제).
                    9. 스크랩 검증: {scrap_criteria_text}
                       - 복합수지(PP TD20%, PA66 GF30% 등)로 분쇄재 재사용이 불가한 사출품은 투입량 전체를 재료비로 인정하고 스크랩 환입은 0원 처리.
                       - 금속 프레스/가공/다이캐스팅은 스크랩 매각 환입 필수 반영.

                    [절대 원칙 - 단가 역전 금지]
                    - 협력사가 당사 기준보다 낮게 책정한 항목을 강제로 올려 총 사정가가 협력사 제출가보다 커지는 역전 현상을 절대 발생시키지 마십시오.

                    [출력 형식 가이드]
                    반드시 유효한 JSON 형식으로만 응답하세요. audit_comment 내부 줄바꿈은 이스케이프(\\\\n) 처리하세요.
                    키 구조:
                    - item_info: supplier, part_name, part_no
                    - comparison: submitted_price, adjusted_price, cost_reduction, reduction_rate
                    - cost_breakdown: 배열 형태, 각 요소는 category, item, submitted, adjusted, diff, note
                      (항목: 투입재료비, 스크랩환입(-), 순재료비, 재료관리비, 직접노무비, 간접제조경비, 제조원가 합계, 일반관리비, 영업이익, 최종 견적 단가)
                    - audit_comment: 갑지/을지 대조 결과, 세부 삭감 사유, 협력사 전달용 공식 공문 문구
                    """
                    contents.append(prompt)

                    for attempt in range(3):
                        try:
                            response = client.models.generate_content(
                                model="gemini-3.6-flash",
                                contents=contents,
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json"
                                )
                            )
                            res_text = response.text.strip()

                            try:
                                data = json.loads(res_text, strict=False)
                            except Exception:
                                clean_text = re.sub(r"^```json\s*", "", res_text)
                                clean_text = re.sub(r"^```\s*", "", clean_text)
                                clean_text = re.sub(r"\s*```$", "", clean_text)
                                data = json.loads(clean_text, strict=False)

                            # 상단 요약 카드
                            comp = data["comparison"]
                            c_sub, c_adj, c_diff, c_rate = st.columns(4)
                            c_sub.metric("협력사 제출가", f"{comp['submitted_price']:,.1f}원")
                            c_adj.metric("당사 사정 목표가", f"{comp['adjusted_price']:,.1f}원")
                            c_diff.metric("절감 가능액", f"-{comp['cost_reduction']:,.1f}원")
                            c_rate.metric("절감율", f"-{comp['reduction_rate']:.1f}%")

                            # 표준 원가계산서 대조 테이블
                            st.markdown("#### 📋 표준 견적 대조 원가계산서 (갑지/을지 종합)")
                            df = pd.DataFrame(data["cost_breakdown"])
                            df.columns = ["구분", "항목", "협력사 제출", "당사 사정가", "차액(절감)", "사정 기준 및 사유"]
                            st.dataframe(df, use_container_width=True, hide_index=True)

                            # CSV 다운로드
                            csv_data = df.to_csv(index=False, encoding="utf-8-sig")
                            st.download_button(
                                label="📥 사정 원가계산서 엑셀(CSV) 다운로드",
                                data=csv_data,
                                file_name="Cost_Audit_Report.csv",
                                mime="text/csv"
                            )
                            st.divider()

                            # 상세 코멘트 출력
                            if "audit_comment" in data and data["audit_comment"]:
                                st.markdown(data["audit_comment"])

                            break
                        except Exception as e:
                            if "503" in str(e) and attempt < 2:
                                time.sleep(3)
                                continue
                            else:
                                st.error(f"분석 중 오류 발생: {e}")
                                break
