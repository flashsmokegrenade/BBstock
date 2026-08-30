import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import re
import argparse
from datetime import datetime

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


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
        # 전체 텍스트 합치기
        raw_text = "".join(self.log)
        # 3개 이상 연속된 개행(\n\n\n...)을 깔끔하게 2개(\n\n)로 압축하고 앞뒤 공백 제거
        cleaned_text = re.sub(r'\n{3,}', '\n\n', raw_text).strip()
        return cleaned_text


def extract_final_decision(full_log: str) -> str:
    match = re.search(r"FINAL TRANSACTION PROPOSAL:\s*\*\*([A-Za-z]+)\*\*", full_log, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    match = re.search(r"================ 최종 결정 ================\s*\n\s*([A-Za-z]+)", full_log, re.IGNORECASE)
    if match:
        return match.group(1).upper()
        
    return "HOLD"


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
        desktop_path = os.path.join(CURRENT_DIR, "desktop_output")

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

    # 끝부분 공백 및 빈 줄 확실하게 정리 후 저장
    clean_log_for_file = full_log.rstrip() + "\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(clean_log_for_file)

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

    logger = DualLogger()
    original_stdout = sys.stdout
    sys.stdout = logger

    success = False
    final_decision = "HOLD"

    try:
        print(f"🚀 분석을 시작합니다... [종목: {args.ticker} | 기준 날짜: {args.date}]")

        config = DEFAULT_CONFIG.copy()
        
        config["memory_log_max_entries"] = 0
        if "enable_memory" in config:
            config["enable_memory"] = False
        
        hybrid_language_instruction = (
            "\n\n[SYSTEM DIRECTION:\n"
            "1. REASONING & DEBATE IN ENGLISH: All internal agent discussions, technical analyses, fundamentals evaluations, domain reports, and intermediate reasoning steps MUST be conducted strictly in English to maximize financial reasoning depth and analytical performance.\n"
            "2. FINAL REPORT IN KOREAN: The 'Final Trading Strategy Report' (including Risk Evaluation, Executive Summary, Investment Thesis, and Final Decision) MUST be written entirely in professional, fluent, and clear Korean.\n"
            "3. NO MEMORY: Do NOT rely on, cite, or retrieve any past memory or historical trade reflections (past_context). Evaluate the ticker strictly and independently based only on the current market data and financial indicators provided for this specific analysis date.]"
        )
        
        if "system_prompt_suffix" in config:
            config["system_prompt_suffix"] += hybrid_language_instruction
        else:
            config["system_prompt_suffix"] = hybrid_language_instruction

        ta = TradingAgentsGraph(debug=True, config=config)
        ta.propagate(args.ticker, args.date)

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
        sys.stdout = original_stdout

        if success:
            save_report_to_desktop(args.ticker, args.date, full_text, final_decision)
        else:
            print("\n⚠️ 분석이 정상 완료되지 않아 파일 저장을 건너뜁니다.")


if __name__ == "__main__":
    main()