from agent.interfaces.queue_consumer import _should_require_review
from agent.storage.audit_store import AuditStore


def test_policy_gate_requires_review_for_high_risk(monkeypatch) -> None:
    monkeypatch.setattr("agent.interfaces.queue_consumer.Config.AUTONOMY_REQUIRE_REVIEW_ON_HIGH_RISK", True)
    job = {"risk_label": "high"}
    result = {"confidence_score": 0.95, "anomalia_detectada": False}

    required, reason = _should_require_review(job, result)
    assert required is True
    assert "high risk" in reason


def test_policy_gate_requires_review_for_low_confidence(monkeypatch) -> None:
    monkeypatch.setattr("agent.interfaces.queue_consumer.Config.AUTONOMY_REQUIRE_REVIEW_ON_HIGH_RISK", False)
    monkeypatch.setattr("agent.interfaces.queue_consumer.Config.AUTONOMY_REVIEW_CONFIDENCE_THRESHOLD", 0.8)
    job = {"risk_label": "low"}
    result = {"confidence_score": 0.5, "anomalia_detectada": False}

    required, reason = _should_require_review(job, result)
    assert required is True
    assert "low confidence" in reason


def test_store_marks_review_required(tmp_path) -> None:
    store = AuditStore(str(tmp_path / "review.db"))
    job_id = store.enqueue_file_job(str(tmp_path / "exam.json"), {}, priority_score=0.5, risk_label="medium")
    claimed = store.claim_next_job()
    assert claimed is not None and int(claimed["id"]) == job_id

    store.mark_job_review_required(job_id, "Policy test")
    stats = store.get_job_stats()
    assert stats["review_required"] == 1
