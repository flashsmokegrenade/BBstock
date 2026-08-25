from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import DomainReport, render_domain_report
from tradingagents.agents.utils.agent_utils import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        # DomainReport 형식을 유도하도록 시스템 메시지 가이드 수정
        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. "
            "Please analyze the company's fundamental information such as financial documents, company profile, basic company financials, "
            "and company financial history to gain a full view of the company's fundamental information to inform traders. "
            "You must provide your final output conforming to the DomainReport schema containing: "
            "1. analyst_findings (objective data, metrics, and facts summarized), "
            "2. debate_summary (perspectives on strengths, weaknesses, valuation, or risks), "
            "3. bull_score (0-100 integer score representing fundamental strength/bullishness), "
            "4. bear_score (0-100 integer score representing fundamental risks/bearishness)."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction(),
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # 도구 호출 및 구조화된 출력을 동시에 바인딩
        # 참고: LangGraph/LangChain 구조상 도구 사용과 구조화된 출력이 함께 쓰이거나, 
        # 혹은 도구 호출 루프 이후 최종 출력이 DomainReport로 렌더링되도록 처리됩니다.
        formatted_messages = prompt.format_messages(messages=state["messages"])
        
        # 기본 체인으로 우선 도구 실행 결과를 포함한 메시지를 얻거나, 
        # 프레임워크의 구조화 유틸리티를 활용해 DomainReport로 출력 강제
        structured_llm = bind_structured(llm, DomainReport, "Fundamentals Analyst")
        
        # 기존 코드의 tool execution 흐름을 유지하면서 최종 리포트를 DomainReport로 렌더링
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            # 만약 도구 호출이 끝나고 최종 텍스트가 나오는 단계라면 구조화 파싱 시도 또는 렌더링 적용
            report = result.content
        else:
            # 도구 호출이 진행 중인 중간 단계의 메시지일 경우
            report = result.content

        # 만약 최종 결과물 형태로 파싱이 필요한 경우 render_domain_report 적용
        # (framework 구조에 맞춰 반환값 포맷 통일)
        final_report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            lambda r: render_domain_report("Fundamental", r),
            "Fundamentals Analyst",
        ) if len(result.tool_calls) == 0 else report

        return {
            "messages": [result],
            "fundamentals_report": final_report_text,
        }

    return fundamentals_analyst_node