"""Polymarket prediction-market vendor (Bypassed due to 451 Regional Restriction)."""

import logging

logger = logging.getLogger(__name__)

def get_prediction_markets(topic: str, limit: int | None = None) -> str:
    """
    Bypass Polymarket API calls to prevent 451 legal restriction errors 
    and speed up analysis.
    """
    logger.info("Polymarket search bypassed for topic: %r", topic)
    return (
        f"Polymarket data is bypassed due to regional network restrictions. "
        f"Proceed without prediction-market signal for '{topic}'."
    )