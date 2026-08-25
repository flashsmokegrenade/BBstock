import os
import sys
import re
import argparse
from datetime import datetime

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


# 1. 터미널 출력과 텍스트 버퍼를 동시에 기록하는 로거
class DualLogger:
    def __init__(self):
        self.terminal = sys.stdout
        self.log = []

    def write(self, message):
        self.terminal.write(message)
        self.log.append(message)

    def flush(self):
        self.terminal.flush()

    def get_content(self):
        return "".join(self.log)


# 2. 리포트 본문에서 실제 최종 결정을 정확히 추출하는 함수
def extract_final_decision(full_log: str) -> str:
    match = re.search(r"FINAL TRANSACTION PROPOSAL:\s*\*\*([A-Za-z]+)\*\*", full_log, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    match = re.search(r"================ 최종 결정 ================\s*\n\s*([A-Za-z]+)", full_log, re.IGNORECASE)
    if match:
        return match.group(1).upper()
        
    return "HOLD"


# 3. 최종 결정을 판별하여 바탕화면 3개 폴더에 분류 저장하는 함수
def save_report_to_desktop(ticker: str, target_date: str, full_log: str, final_decision: str):
    user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))

    candidate_paths = [
        os.path.join(user_profile, "OneDrive", "Desktop"),
        os.path.join(user_profile, "OneDrive", "바탕 화면"),
        os.path.join(user_profile, "Desktop"),
        os.path.join(user_profile, "바탕 화면"),
    ]

    desktop_path = None
    for path in candidate_paths:
        if os.path.exists(path):
            desktop_path = path
            break

    if not desktop_path:
        desktop_path = os.path.join(user_profile, "Desktop")

    base_dir = os.path.join(desktop_path, "stock_db")
    folder_map = {
        "BUY_OVERWEIGHT": os.path.join(base_dir, "1_Buy_Overweight"),
        "HOLD": os.path.join(base_dir, "2_Hold"),
        "SELL_UNDERWEIGHT": os.path.join(base_dir, "3_Sell_Underweight"),
    }

    for path in folder_map.values():
        os.makedirs(path, exist_ok=True)

    if final_decision in ["BUY", "OVERWEIGHT"]:
        target_folder = folder_map["BUY_OVERWEIGHT"]
    elif final_decision in ["SELL", "UNDERWEIGHT"]:
        target_folder = folder_map["SELL_UNDERWEIGHT"]
    else:
        target_folder = folder_map["HOLD"]
        final_decision = "HOLD"

    timestamp = datetime.now().strftime("%H%M%S")
    file_name = f"[{target_date}] {ticker}_{final_decision}_{timestamp}.txt"
    file_path = os.path.join(target_folder, file_name)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_log)

    print(f"\n[📁 자동 저장 완료] 리포트가 성공적으로 분류 저장되었습니다:")
    print(f"-> 저장 경로: {file_path}")


def main():
    today_str = datetime.now().strftime("%Y-%m-%d")

    parser = argparse.ArgumentParser(description="TradingAgents")
    parser.add_argument("--ticker", type=str, required=True, help="Stock ticker symbol")
    parser.add_argument("--date", type=str, default=today_str, help="Analysis date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--models", type=str, default="gpt-4o-mini", help="LLM model to use")
    parser.add_argument("--rounds", type=int, default=2, help="Number of rounds")
    
    args = parser.parse_args()

    # 실시간 콘솔 출력 + 텍스트 가로채기 활성화
    logger = DualLogger()
    original_stdout = sys.stdout
    sys.stdout = logger

    success = False
    final_decision = "HOLD"

    try:
        print(f"🚀 분석을 시작합니다... [종목: {args.ticker} | 기준 날짜: {args.date}]")

        config = DEFAULT_CONFIG.copy()
        
        # [핵심 1] 과거 기록 메모리 주입 개수를 0으로 설정하여 로딩 차단
        config["memory_log_max_entries"] = 0
        if "enable_memory" in config:
            config["enable_memory"] = False
        
        # [핵심 2] 한국어 지침 + 과거 기록 무시 및 독립 분석 지침 결합
        korean_and_no_memory_instruction = (
            "\n\n[SYSTEM DIRECTION:\n"
            "1. You must conduct all conversations, tool summaries, reasoning steps, and final output reports entirely in Korean.\n"
            "모든 분석 과정, 에이전트 간의 대화, 이유(Reasoning), 기술/재무 지표 요약 설명, 그리고 최종 결정(FINAL TRANSACTION PROPOSAL) 리포트를 반드시 완벽한 한국어로만 작성해 주세요.\n"
            "2. Do NOT rely on, cite, or retrieve any past memory or historical trade reflections (past_context). Evaluate the ticker strictly and independently based only on the current market data and financial indicators provided for this specific analysis date.]"
        )
        
        if "system_prompt_suffix" in config:
            config["system_prompt_suffix"] += korean_and_no_memory_instruction
        else:
            config["system_prompt_suffix"] = korean_and_no_memory_instruction

        # 그래프 초기화 및 구동
        ta = TradingAgentsGraph(debug=True, config=config)
        ta.propagate(args.ticker, args.date)

        # 버퍼에 쌓인 전체 리포트 본문에서 실제 최종 결정을 추출
        full_text = logger.get_content()
        final_decision = extract_final_decision(full_text)
        
        print("\n================ 최종 결정 ================")
        print(f"최종 투자의견: {final_decision}")
        print("===========================================")
        
        success = True

    except Exception as e:
        print(f"\n❌ [오류 발생] 분석 중 문제가 발생했습니다: {e}")

    finally:
        full_text = logger.get_content()
        sys.stdout = original_stdout  # 터미널 출력 복원

        # 분석이 에러 없이 정상적으로 끝났을 때만 파일 저장
        if success:
            save_report_to_desktop(args.ticker, args.date, full_text, final_decision)
        else:
            print("\n⚠️ 분석이 정상 완료되지 않아 파일 저장을 건너뜁니다.")


if __name__ == "__main__":
    main()