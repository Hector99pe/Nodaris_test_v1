"""Resilience utilities for LLM access in Nodaris."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from agent.config import Config


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the LLM circuit breaker is open and rejects a request."""

    def __init__(self, retry_after_sec: float, message: str | None = None) -> None:
        """Initialize circuit breaker open exception with retry time."""
        self.retry_after_sec = max(0.0, float(retry_after_sec))
        super().__init__(message or f"Circuit breaker LLM abierto; reintentar en {self.retry_after_sec:.1f}s")


class LlmCircuitBreaker:
    """In-process circuit breaker with retries and exponential backoff."""

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        """Initialize circuit breaker with optional clock and sleeper dependencies."""
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Reset circuit breaker to closed state and clear failure counters."""
        with self._lock:
            self._state = "closed"
            self._consecutive_failures = 0
            self._opened_until = 0.0
            self._last_error = ""

    def snapshot(self) -> dict[str, Any]:
        """Return current circuit breaker state snapshot."""
        with self._lock:
            retry_after = max(0.0, self._opened_until - self._clock()) if self._state == "open" else 0.0
            return {
                "state": self._state,
                "consecutive_failures": self._consecutive_failures,
                "retry_after_sec": round(retry_after, 3),
                "last_error": self._last_error,
            }

    def call(self, operation: Callable[[], Any]) -> Any:
        """Execute operation with circuit breaker, retries, and exponential backoff."""
        max_attempts = max(1, int(Config.LLM_CIRCUIT_BREAKER_MAX_RETRIES) + 1)
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            self._ensure_request_allowed()
            try:
                result = operation()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._record_failure(exc)
                if attempt >= max_attempts - 1:
                    raise
                if self.snapshot()["state"] == "open":
                    raise
                delay = float(Config.LLM_CIRCUIT_BREAKER_BASE_DELAY_SEC) * (2 ** attempt)
                self._sleep(max(0.0, delay))
                continue

            self._record_success()
            return result

        if last_error is not None:
            raise last_error
        raise RuntimeError("Circuit breaker LLM no pudo ejecutar la operación")

    def _ensure_request_allowed(self) -> None:
        with self._lock:
            if self._state != "open":
                return
            remaining = self._opened_until - self._clock()
            if remaining > 0:
                raise CircuitBreakerOpenError(remaining)
            self._state = "half_open"

    def _record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._consecutive_failures = 0
            self._opened_until = 0.0
            self._last_error = ""

    def _record_failure(self, exc: Exception) -> None:
        threshold = max(1, int(Config.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD))
        reset_sec = max(1, int(Config.LLM_CIRCUIT_BREAKER_RESET_SEC))
        with self._lock:
            self._consecutive_failures += 1
            self._last_error = str(exc)
            if self._state == "half_open" or self._consecutive_failures >= threshold:
                self._state = "open"
                self._opened_until = self._clock() + reset_sec
            else:
                self._state = "closed"


_LLM_CIRCUIT_BREAKER = LlmCircuitBreaker()


def call_with_llm_circuit_breaker(operation: Callable[[], Any]) -> Any:
    """Execute an LLM operation through the shared circuit breaker."""
    return _LLM_CIRCUIT_BREAKER.call(operation)


def reset_llm_circuit_breaker() -> None:
    """Reset the shared LLM circuit breaker state."""
    _LLM_CIRCUIT_BREAKER.reset()


def get_llm_circuit_breaker_snapshot() -> dict[str, Any]:
    """Return the current shared circuit breaker state."""
    return _LLM_CIRCUIT_BREAKER.snapshot()


def format_llm_circuit_breaker_message(exc: CircuitBreakerOpenError) -> str:
    """Build a user-facing message for an open LLM circuit breaker."""
    wait_sec = max(1, int(round(exc.retry_after_sec)))
    return (
        "El motor de IA está temporalmente protegido por circuit breaker "
        f"tras varios fallos consecutivos. Reintenta en {wait_sec}s."
    )
