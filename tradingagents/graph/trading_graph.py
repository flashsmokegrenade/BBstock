# TradingAgents/graph/trading_graph.py

import json
import logging
import os
import contextlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yfinance as yf
from langgraph.prebuilt import ToolNode

# ================= [추가된 부분: yfinance 시스템 에러 로그 화면 출력 완벽 차단] =================
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
# ==================================================================================================

# Import the abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_insider_transactions,
    get_macro_indicators,
    get_news,
    get_prediction_markets,
    get_stock_data,
    get_verified_market_snapshot,
    resolve_instrument_identity,
)
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.reporting import write_report_tree

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .reflection import Reflector
from .setup import GraphSetup
from .signal_processing import SignalProcessor

logger = logging.getLogger(__name__)


def _coerce_max_retries(value):
    """Validate an ``llm_max_retries`` value to a non-negative int."""
    if isinstance(value, bool):
        raise ValueError(f"llm_max_retries must be an integer, not a boolean: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"llm_max_retries must be an integer, got {value!r}") from exc
    if n < 0:
        raise ValueError(f"llm_max_retries must be >= 0, got {n}")
    return n


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
    ):
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        set_config(self.config)

        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        llm_kwargs = self._get_provider_kwargs()

        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        self.memory_log = TradingMemoryLog(self.config)
        self.tool_nodes = self._create_tool_nodes()

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}

        self.selected_analysts = tuple(selected_analysts)
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> dict[str, Any]:
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level
        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        temperature = self.config.get("temperature")
        if temperature is not None and temperature != "":
            kwargs["temperature"] = float(temperature)

        max_retries = self.config.get("llm_max_retries")
        if max_retries is not None and max_retries != "":
            kwargs["max_retries"] = _coerce_max_retries(max_retries)

        return kwargs

    def _create_tool_nodes(self) -> dict[str, ToolNode]:
        return {
            "market": ToolNode([get_stock_data, get_indicators, get_verified_market_snapshot]),
            "social": ToolNode([get_news]),
            "news": ToolNode([get_news, get_global_news, get_insider_transactions, get_macro_indicators, get_prediction_markets]),
            "fundamentals": ToolNode([get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]),
        }

    def _resolve_benchmark(self, ticker: str) -> str:
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return explicit
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        for suffix, benchmark in benchmark_map.items():
            if suffix and ticker_upper.endswith(suffix.upper()):
                return benchmark
        return benchmark_map.get("", "SPY")

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5,
        benchmark: str = "SPY",
    ) -> tuple[float | None, float | None, int | None]:
        from tradingagents.dataflows.symbol_utils import normalize_symbol

        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)
            end_str = end.strftime("%Y-%m-%d")

            # yfinance 에러 메시지 원천 차단
            with open(os.devnull, 'w') as devnull:
                with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                    stock = yf.Ticker(normalize_symbol(ticker)).history(start=trade_date, end=end_str)
                    bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(bench) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
            raw = float((stock["Close"].iloc[actual_days] - stock["Close"].iloc[0]) / stock["Close"].iloc[0])
            bench_ret = float((bench["Close"].iloc[actual_days] - bench["Close"].iloc[0]) / bench["Close"].iloc[0])
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning("Could not resolve outcome for %s on %s vs %s: %s", ticker, trade_date, benchmark, e)
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        benchmark = self._resolve_benchmark(ticker)
        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(ticker, entry["date"], benchmark=benchmark)
            if raw is None:
                continue
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def resolve_instrument_context(self, ticker: str, asset_type: str = "stock") -> str:
        identity = resolve_instrument_identity(ticker)
        return build_instrument_context(ticker, asset_type, identity)

    def _run_signature(self, asset_type: str) -> str:
        return "|".join([
            "analysts=" + ",".join(self.selected_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
        ])

    def propagate(self, company_name, trade_date, asset_type: str = "stock"):
        # 순수한 티커명만 저장하여 API 호출 시 URL 깨짐 방지
        self.ticker = company_name.split('\n')[0].strip()

        self._resolve_pending_entries(self.ticker)

        if self.config.get("checkpoint_enabled"):
            self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], self.ticker)
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                self.config["data_cache_dir"], self.ticker, str(trade_date),
                self._run_signature(asset_type),
            )
            if step is not None:
                logger.info("Resuming from step %d for %s on %s", step, self.ticker, trade_date)
            else:
                logger.info("Starting fresh for %s on %s", self.ticker, trade_date)

        try:
            return self._run_graph(self.ticker, trade_date, asset_type=asset_type)
        finally:
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def save_reports(self, final_state, ticker, save_path=None) -> Path:
        if save_path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = (Path(self.config["results_dir"]) / "reports" / f"{safe_ticker_component(ticker)}_{stamp}")
        return write_report_tree(final_state, ticker, save_path)

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock"):
        """Execute the graph and write the resulting state to disk and memory log."""
        import sys

        # 1. API 호출 오류를 막기 위해 순수 티커명만 추출합니다.
        pure_company = company_name.split('\n')[0].strip()

        past_context = self.memory_log.get_past_context(pure_company)
        instrument_context = self.resolve_instrument_context(pure_company, asset_type)

        # 2. State 생성 시 순수 티커명만 전달
        init_agent_state = self.propagator.create_initial_state(
            pure_company,
            trade_date,
            asset_type=asset_type,
            past_context=past_context,
            instrument_context=instrument_context,
        )
        args = self.propagator.get_graph_args()

        if self.config.get("checkpoint_enabled"):
            tid = thread_id(pure_company, str(trade_date), self._run_signature(asset_type))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        # ================= [완벽히 통제된 디버그 출력 블록] =================
        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if chunk.get("messages"):
                    msg = chunk["messages"][-1]
                    
                    msg_type = getattr(msg, "type", "")
                    msg_class = type(msg).__name__
                    content = getattr(msg, "content", "")

                    if msg_type == "tool" or msg_class == "ToolMessage" or getattr(msg, "tool_calls", None):
                        trace.append(chunk)
                        continue
                        
                    if not content or not isinstance(content, str):
                        trace.append(chunk)
                        continue

                    system_noise_keywords = [
                        "Use this snapshot as the source of truth",
                        "Human Message",
                        "Tool Calls:",
                        "Tool Message",
                        "get_verified_market_snapshot",
                        "Proceed with your assigned analysis",
                        "possibly delisted",
                        "Yahoo error",
                        "call_ID:",
                        "Call ID:"
                    ]
                    if any(keyword in content for keyword in system_noise_keywords):
                        trace.append(chunk)
                        continue

                    trace.append(chunk)
                    
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(init_agent_state, **args)
        # =====================================================================

        self.curr_state = final_state

        # ================= [비용 0원: 순수 파이썬 문자열 필터링만 적용 (LLM 미호출)] =================
        try:
            report_keys = ["market_report", "sentiment_report", "news_report", "fundamentals_report", "final_trade_decision"]
            
            for r_key in report_keys:
                content = final_state.get(r_key, "")
                if content:
                    # 가짜 데이터가 포함된 줄만 삭제 (API 비용 발생 안 함)
                    if "2023" in content:
                        lines = content.split('\n')
                        clean_lines = [l for l in lines if not any(x in l for x in ["2023", "AAPL", "MSFT", "GOOG"])]
                        content = '\n'.join(clean_lines)
                    
                    final_state[r_key] = content

        except Exception as filter_error:
            logger.warning("전체 보고서 필터링 과정에서 예외 발생: %s", filter_error)

        # ================= [영문 리포트 터미널 출력] =================
        report_titles = {
            "market_report": "Technical Analysis Report",
            "sentiment_report": "Social Sentiment Report",
            "news_report": "Macro & News Report",
            "fundamentals_report": "Fundamentals Report",
            "final_trade_decision": "Final Trading Strategy Report"
        }
        for r_key, title_name in report_titles.items():
            clean_content = final_state.get(r_key, "")
            if clean_content:
                sys.stdout.write(f"\n{'='*50}\n[{title_name}]\n{'='*50}\n{clean_content.strip()}\n")
                sys.stdout.flush()

        # ================= [디스크에 데이터 기록] =================
        self._log_state(trade_date, final_state)

        self.memory_log.store_decision(
            ticker=pure_company,
            trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )

        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], pure_company, str(trade_date),
                self._run_signature(asset_type),
            )

        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "investment_debate_state": {
                "bull_history": final_state.get("investment_debate_state", {}).get("bull_history", []),
                "bear_history": final_state.get("investment_debate_state", {}).get("bear_history", []),
                "history": final_state.get("investment_debate_state", {}).get("history", []),
                "current_response": final_state.get("investment_debate_state", {}).get("current_response", ""),
                "judge_decision": final_state.get("investment_debate_state", {}).get("judge_decision", ""),
            },
            "trader_investment_decision": final_state.get("trader_investment_plan", ""),
            "risk_debate_state": {
                "aggressive_history": final_state.get("risk_debate_state", {}).get("aggressive_history", []),
                "conservative_history": final_state.get("risk_debate_state", {}).get("conservative_history", []),
                "neutral_history": final_state.get("risk_debate_state", {}).get("neutral_history", []),
                "history": final_state.get("risk_debate_state", {}).get("history", []),
                "judge_decision": final_state.get("risk_debate_state", {}).get("judge_decision", ""),
            },
            "investment_plan": final_state.get("investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
        }

        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        return self.signal_processor.process_signal(full_signal)