"""Configuration for Nodaris agent."""

import os
from typing import Optional


class Config:
    """Centralized configuration."""

    # OpenAI settings
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))

    # Academic validation rules
    NOTA_MIN: int = 0
    NOTA_MAX: int = 20

    # Anomaly detection thresholds
    ANOMALY_THRESHOLD: float = 0.7

    # Telegram settings
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")

    # LangSmith tracing
    LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
