from pathlib import Path

import pytest

from agent.resilience import CircuitBreakerOpenError, LlmCircuitBreaker


def _raise_runtime_error(message: str):
    raise RuntimeError(message)


def test_llm_circuit_breaker_opens_after_threshold(monkeypatch) -> None:
    now = [100.0]
    sleeper_calls: list[float] = []
    breaker = LlmCircuitBreaker(clock=lambda: now[0], sleeper=lambda delay: sleeper_calls.append(delay))

    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_RESET_SEC", 30)
    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_MAX_RETRIES", 0)
    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_BASE_DELAY_SEC", 0.1)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: _raise_runtime_error("boom-1"))

    assert breaker.snapshot()["state"] == "closed"
    assert breaker.snapshot()["consecutive_failures"] == 1

    with pytest.raises(RuntimeError):
        breaker.call(lambda: _raise_runtime_error("boom-2"))

    snapshot = breaker.snapshot()
    assert snapshot["state"] == "open"
    assert snapshot["consecutive_failures"] == 2
    assert abs(float(snapshot["retry_after_sec"]) - 30.0) < 1e-9
    assert sleeper_calls == []

    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(lambda: "should not run")


def test_llm_circuit_breaker_recovers_after_reset_window(monkeypatch) -> None:
    now = [200.0]
    breaker = LlmCircuitBreaker(clock=lambda: now[0], sleeper=lambda _: None)

    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 1)
    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_RESET_SEC", 15)
    monkeypatch.setattr("agent.resilience.Config.LLM_CIRCUIT_BREAKER_MAX_RETRIES", 0)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: _raise_runtime_error("outage"))

    assert breaker.snapshot()["state"] == "open"

    now[0] += 16
    result = breaker.call(lambda: "ok")

    assert result == "ok"
    snapshot = breaker.snapshot()
    assert snapshot["state"] == "closed"
    assert snapshot["consecutive_failures"] == 0
    assert abs(float(snapshot["retry_after_sec"]) - 0.0) < 1e-9


@pytest.mark.anyio
async def test_consumer_requeues_job_when_circuit_breaker_is_open(monkeypatch, tmp_path: Path) -> None:
    from agent.interfaces import queue_consumer
    from agent.storage.audit_store import AuditStore

    store = AuditStore(str(tmp_path / "consumer_breaker.db"))
    file_path = tmp_path / "exam.json"
    file_path.write_text("{}", encoding="utf-8")
    job_id = store.enqueue_file_job(str(file_path), {}, priority_score=0.5, risk_label="medium")

    async def _raise_open(*_args, **_kwargs):
        raise CircuitBreakerOpenError(12)

    async def _astream_raise(*_args, **_kwargs):
        raise CircuitBreakerOpenError(12)
        yield  # make it an async generator

    monkeypatch.setattr(queue_consumer, "AuditStore", lambda: store)
    monkeypatch.setattr(queue_consumer.graph, "astream", _astream_raise)

    processed = await queue_consumer.consume_once()

    assert processed == "released"
    stats = store.get_job_stats()
    assert stats["pending"] == 1
    assert stats["failed"] == 0
    assert store.get_dead_letter_count() == 0

    claimed = store.claim_next_job()
    assert claimed is not None
    assert claimed["id"] == job_id
    assert claimed["attempt_count"] == 1
