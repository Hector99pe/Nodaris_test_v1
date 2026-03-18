"""Configuration for Nodaris agent."""

import os
from typing import Optional


class Config:
    """Centralized configuration."""

    # OpenAI settings
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))

    # Academic validation rules
    NOTA_MIN: int = 0
    NOTA_MAX: int = 20

    # Anomaly detection thresholds
    ANOMALY_THRESHOLD: float = 0.7

    # Telegram settings
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")

    # Superdapp settings
    SUPERDAPP_API_KEY: Optional[str] = os.getenv("SUPERDAPP_API_KEY")
    SUPERDAPP_API_URL: str = os.getenv("SUPERDAPP_API_URL", "https://api.superdapp.ai")
    SUPERDAPP_WEBHOOK_SECRET: Optional[str] = os.getenv("SUPERDAPP_WEBHOOK_SECRET")
    # Railway asigna PORT automáticamente, usar ese si existe
    SUPERDAPP_WEBHOOK_PORT: int = int(os.getenv("PORT", "8080"))
    SUPERDAPP_WEBHOOK_PATH: str = os.getenv("SUPERDAPP_WEBHOOK_PATH", "/superdapp/webhook")
    SUPERDAPP_SEND_ENDPOINT: str = os.getenv("SUPERDAPP_SEND_ENDPOINT", "/messages")
    SUPERDAPP_DEBUG_WEBHOOK: bool = os.getenv("SUPERDAPP_DEBUG_WEBHOOK", "false").lower() == "true"
    SUPERDAPP_ASYNC_DELIVERY_ENABLED: bool = os.getenv(
        "SUPERDAPP_ASYNC_DELIVERY_ENABLED", "false"
    ).lower() == "true"

    # LangSmith tracing
    LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    # Agent autonomy and guardrails
    ALLOW_HUMAN_INTERRUPT: bool = os.getenv("ALLOW_HUMAN_INTERRUPT", "false").lower() == "true"
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "15"))
    MAX_REFLECTION_REPLANS: int = int(os.getenv("MAX_REFLECTION_REPLANS", "3"))

    # Persistence
    AUDIT_DB_PATH: str = os.getenv("AUDIT_DB_PATH", "data/nodaris_audits.db")

    # Autonomous discovery/scheduling
    AUTONOMY_ENABLED: bool = os.getenv("AUTONOMY_ENABLED", "false").lower() == "true"
    AUTONOMY_INBOX_PATH: str = os.getenv("AUTONOMY_INBOX_PATH", "data/inbox")
    AUTONOMY_SCHEDULER_INTERVAL_SEC: int = int(os.getenv("AUTONOMY_SCHEDULER_INTERVAL_SEC", "300"))
    AUTONOMY_CONSUMER_BATCH_SIZE: int = int(os.getenv("AUTONOMY_CONSUMER_BATCH_SIZE", "5"))
    AUTONOMY_MAX_JOB_RETRIES: int = int(os.getenv("AUTONOMY_MAX_JOB_RETRIES", "2"))
    AUTONOMY_PROCESSED_PATH: str = os.getenv("AUTONOMY_PROCESSED_PATH", "data/processed")
    AUTONOMY_FAILED_PATH: str = os.getenv("AUTONOMY_FAILED_PATH", "data/failed")
    AUTONOMY_REVIEW_PATH: str = os.getenv("AUTONOMY_REVIEW_PATH", "data/review")
    AUTONOMY_JOB_TIMEOUT_SEC: int = int(os.getenv("AUTONOMY_JOB_TIMEOUT_SEC", "180"))
    AUTONOMY_DEADLETTER_MAX_ITEMS: int = int(os.getenv("AUTONOMY_DEADLETTER_MAX_ITEMS", "5000"))
    AUTONOMY_REQUIRE_REVIEW_ON_HIGH_RISK: bool = (
        os.getenv("AUTONOMY_REQUIRE_REVIEW_ON_HIGH_RISK", "true").lower() == "true"
    )
    AUTONOMY_REVIEW_CONFIDENCE_THRESHOLD: float = float(
        os.getenv("AUTONOMY_REVIEW_CONFIDENCE_THRESHOLD", "0.75")
    )

    # LLM resilience
    LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = int(
        os.getenv("LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3")
    )
    LLM_CIRCUIT_BREAKER_RESET_SEC: int = int(
        os.getenv("LLM_CIRCUIT_BREAKER_RESET_SEC", "60")
    )
    LLM_CIRCUIT_BREAKER_MAX_RETRIES: int = int(
        os.getenv("LLM_CIRCUIT_BREAKER_MAX_RETRIES", "2")
    )
    LLM_CIRCUIT_BREAKER_BASE_DELAY_SEC: float = float(
        os.getenv("LLM_CIRCUIT_BREAKER_BASE_DELAY_SEC", "1.0")
    )

    # Learning memory
    LEARNING_MEMORY_ENABLED: bool = os.getenv("LEARNING_MEMORY_ENABLED", "true").lower() == "true"
    LEARNING_MEMORY_TOP_TOOLS: int = int(os.getenv("LEARNING_MEMORY_TOP_TOOLS", "3"))

    # Admin notifications
    TELEGRAM_ADMIN_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
