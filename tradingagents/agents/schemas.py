"""Pydantic schemas used by agents that produce structured output."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_NULLISH_FLOAT = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown"}

def _coerce_optional_float(value):
    if isinstance(value, str) and value.strip().lower() in _NULLISH_FLOAT:
        return None
    return value

# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------

class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"

class TraderAction(str, Enum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"

# ---------------------------------------------------------------------------
# 1~4. 4대 핵심 도메인 (Macro, Fundamental, Sentiment, News) 공통 스키마
# ---------------------------------------------------------------------------

class DomainReport(BaseModel):
    """Structured report produced by the 4 Domain Analysts.
    
    Replaces the individual legacy schemas to strictly enforce the Bull/Bear 
    scoring and debate structure required for the 4-Phase Architecture.
    """
    
    analyst_findings: str = Field(
        description="Key objective data, metrics, and facts summarized by the analyst. 4-6 sentences.",
    )
    debate_summary: str = Field(
        description="Summary of the arguments between the Bullish and Bearish researchers regarding these findings.",
    )
    bull_score: int = Field(
        ge=0,
        le=100,
        description="Bullish intensity score from 0 to 100.",
    )
    bear_score: int = Field(
        ge=0,
        le=100,
        description="Bearish intensity score from 0 to 100. (Usually 100 - bull_score)",
    )

def render_domain_report(domain_name: str, report: DomainReport) -> str:
    """Render a DomainReport to the requested markdown format."""
    return "\n".join([
        f"### {domain_name} Analysis",
        f"**Analyst Findings**: {report.analyst_findings}",
        "",
        f"**Debate Summary**: {report.debate_summary}",
        "",
        f"**Domain Score**: [Bull Score: 📈 {report.bull_score} / Bear Score: 📉 {report.bear_score}]",
        "---"
    ])

# ---------------------------------------------------------------------------
# 5. Trader's Initial Strategy (Trader)
# ---------------------------------------------------------------------------

class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader."""

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The synthesis of the 4 Domain Bull/Bear scores and the resulting "
            "initial trading strategy. Formulate the core logic for entry/exit."
        ),
    )
    entry_price: float | None = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: float | None = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )

    @field_validator("entry_price", "stop_loss", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)

def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render TraderProposal as the 5th section: Trader's Initial Strategy & Summary."""
    parts = [
        "### Trader's Initial Strategy & Summary",
        f"**Initial Action**: {proposal.action.value}",
        "",
        f"**Score Synthesis & Rationale**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    
    parts.append("---")
    return "\n".join(parts)

# ---------------------------------------------------------------------------
# 6. Final Execution & Conclusion (Portfolio Manager)
# ---------------------------------------------------------------------------

class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager."""

    rating: PortfolioRating = Field(
        description="The final position rating. Exactly one of Buy / Overweight / Hold / Underweight / Sell.",
    )
    risk_evaluation: str = Field(
        description="Summary of the Risk Management Team's evaluation of the Trader's initial strategy.",
    )
    executive_summary: str = Field(
        description="A concise action plan covering entry strategy, position sizing, and key risk levels.",
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in the 4 Domain scores and risk debate. "
            "MUST incorporate past_context (lessons from prior outcomes) if provided."
        ),
    )

def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision to match the final execution section.
    
    Includes the critical FINAL TRANSACTION PROPOSAL string required by the
    legacy signal processors and memory log components.
    """
    parts = [
        "### Final Execution & Conclusion",
        f"**Risk Evaluation**: {decision.risk_evaluation}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
        "",
        "================ 최종 결정 ================",
        f"FINAL TRANSACTION PROPOSAL: **{decision.rating.value.upper()}**",
        "==========================================="
    ]
    return "\n".join(parts)
# ---------------------------------------------------------------------------
# Research Manager (호환성 및 스키마 유지)
# ---------------------------------------------------------------------------

class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager."""

    recommendation: PortfolioRating = Field(
        description="The investment recommendation. Exactly one of Buy / Overweight / Hold / Underweight / Sell.",
    )
    rationale: str = Field(
        description="Conversational summary of the key points from both sides of the debate, ending with which arguments led to the recommendation.",
    )
    strategic_actions: str = Field(
        description="Concrete steps for the trader or portfolio manager to implement the recommendation.",
    )

def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for downstream consumption."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])