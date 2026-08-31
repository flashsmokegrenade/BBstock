import os
import sys
from datetime import datetime
import streamlit as st

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# 웹 페이지 레이아웃 설정
st.set_page_config(
    page_title="TradingAgents AI 리서치",
    page_icon="📈",
    layout="wide"
)

st.title("🤖 TradingAgents 멀티 에이전트 주식 분석")
st.markdown("10명의 전문 AI 에이전트가 기술적 지표, 재무제표, 매크로 뉴스, 소셜 심리를 종합 분석하여 심층 투자 전략을 제시합니다.")

# 사이드바 설정
st.sidebar.header("⚙️ 분석 설정")
ticker_input = st.sidebar.text_input("종목 티커 (Ticker)", value="TSLA", help="예: TSLA, AAPL, NVDA, MSFT").upper().strip()
target_date = st.sidebar.date_input("기준 날짜", value=datetime.today()).strftime("%Y-%m-%d")

start_btn = st.sidebar.button("🚀 분석 시작", type="primary", use_container_width=True)

if start_btn:
    if not ticker_input:
        st.warning("종목 티커를 입력해 주세요.")
    else:
        with st.spinner(f"⏳ {ticker_input} 분석 중... (에이전트들이 데이터를 수집하고 토론을 진행하고 있습니다. 약 1~2분 소요)"):
            try:
                config = DEFAULT_CONFIG.copy()
                config["max_debate_rounds"] = 1
                config["max_risk_discuss_rounds"] = 1
                config["memory_log_max_entries"] = 0
                if "enable_memory" in config:
                    config["enable_memory"] = False

                hybrid_language_instruction = (
                    "\n\n[SYSTEM DIRECTION:\n"
                    "1. REASONING & DEBATE IN ENGLISH: All internal agent discussions, technical analyses, fundamentals evaluations, domain reports, and intermediate reasoning steps MUST be conducted strictly in English.\n"
                    "2. FINAL REPORT IN KOREAN: The 'Final Trading Strategy Report' (including Risk Evaluation, Executive Summary, Investment Thesis, and Final Decision) MUST be written entirely in professional, fluent, and clear Korean.\n"
                    "3. NO MEMORY: Evaluate strictly based only on current market data.]"
                )
                config["system_prompt_suffix"] = hybrid_language_instruction

                ta = TradingAgentsGraph(debug=False, config=config)
                final_state, decision = ta.propagate(ticker_input, target_date)

                st.success("✅ 분석 완료!")

                # 최종 결정 뱃지 및 결론 표시
                final_report = final_state.get("final_trade_decision", "")
                st.subheader(f"🎯 최종 투자 전략: {decision}")

                if final_report:
                    st.markdown("### 📝 최종 종합 투자 보고서")
                    st.markdown(final_report)

                st.divider()

                # 도메인별 세부 분석 아코디언
                st.subheader("📑 도메인별 세부 분석 리포트")
                col1, col2 = st.columns(2)

                with col1:
                    with st.expander("📈 기술적 분석 (Technical Analysis)", expanded=False):
                        st.markdown(final_state.get("market_report", "데이터 없음"))

                    with st.expander("💬 소셜 미디어 심리 (Social Sentiment)", expanded=False):
                        st.markdown(final_state.get("sentiment_report", "데이터 없음"))

                with col2:
                    with st.expander("📰 글로벌 뉴스 및 매크로 (Macro & News)", expanded=False):
                        st.markdown(final_state.get("news_report", "데이터 없음"))

                    with st.expander("🏢 기업 펀더멘털 및 재무 (Fundamentals)", expanded=False):
                        st.markdown(final_state.get("fundamentals_report", "데이터 없음"))

                # 텍스트 다운로드 버튼 제공
                full_download_text = f"=== {ticker_input} 리서치 리포트 ({target_date}) ===\n\n"
                full_download_text += f"[최종 전략]\n{final_report}\n\n"
                full_download_text += f"[기술적 분석]\n{final_state.get('market_report', '')}\n\n"
                full_download_text += f"[소셜 심리]\n{final_state.get('sentiment_report', '')}\n\n"
                full_download_text += f"[매크로 뉴스]\n{final_state.get('news_report', '')}\n\n"
                full_download_text += f"[재무 분석]\n{final_state.get('fundamentals_report', '')}\n"

                st.download_button(
                    label="📥 전체 리포트 텍스트 다운로드",
                    data=full_download_text,
                    file_name=f"[{target_date}]_{ticker_input}_Report.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"❌ 분석 도중 오류가 발생했습니다: {e}")