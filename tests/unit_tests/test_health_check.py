from agent.interfaces.health_check import FAIL, PASS, WARN, _check_llm_circuit_breaker


def test_health_check_reports_closed_breaker_as_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.interfaces.health_check.get_llm_circuit_breaker_snapshot",
        lambda: {
            "state": "closed",
            "consecutive_failures": 0,
            "retry_after_sec": 0.0,
            "last_error": "",
        },
    )

    result = _check_llm_circuit_breaker()

    assert result["level"] == PASS
    assert result["component"] == "llm.circuit_breaker"
    assert "state=closed" in result["message"]


def test_health_check_reports_degraded_closed_breaker_as_warn(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.interfaces.health_check.get_llm_circuit_breaker_snapshot",
        lambda: {
            "state": "closed",
            "consecutive_failures": 2,
            "retry_after_sec": 0.0,
            "last_error": "timeout",
        },
    )

    result = _check_llm_circuit_breaker()

    assert result["level"] == WARN
    assert "failures=2" in result["message"]


def test_health_check_reports_open_breaker_as_fail(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.interfaces.health_check.get_llm_circuit_breaker_snapshot",
        lambda: {
            "state": "open",
            "consecutive_failures": 3,
            "retry_after_sec": 42.5,
            "last_error": "quota exceeded",
        },
    )

    result = _check_llm_circuit_breaker()

    assert result["level"] == FAIL
    assert "state=open" in result["message"]
    assert "retry_after=42.5s" in result["message"]
    assert "quota exceeded" in result["message"]
