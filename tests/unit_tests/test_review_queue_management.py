from pathlib import Path

from agent.storage.audit_store import AuditStore


def test_review_list_and_decisions(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "review_mgmt.db"))
    file_path = tmp_path / "exam.json"
    file_path.write_text("{}", encoding="utf-8")

    job_id = store.enqueue_file_job(str(file_path), {}, priority_score=0.9, risk_label="high")
    claimed = store.claim_next_job()
    assert claimed is not None and int(claimed["id"]) == job_id

    store.mark_job_review_required(job_id, "policy")
    review_jobs = store.list_review_jobs(limit=10)
    assert len(review_jobs) == 1
    assert review_jobs[0]["id"] == job_id

    store.review_decide(job_id, "approve", "ok")
    stats = store.get_job_stats()
    assert stats["approved"] == 1


def test_update_job_source_ref(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "source_ref.db"))
    file_path = tmp_path / "inbox.json"
    file_path.write_text("{}", encoding="utf-8")

    job_id = store.enqueue_file_job(str(file_path), {}, priority_score=0.2, risk_label="low")
    new_ref = tmp_path / "processed" / "inbox.json"
    new_ref.parent.mkdir(parents=True, exist_ok=True)
    new_ref.write_text("{}", encoding="utf-8")

    store.update_job_source_ref(job_id, str(new_ref))
    recent = store.list_recent_jobs(limit=1)
    assert recent[0]["source_ref"].endswith("inbox.json")


def test_dead_letter_persistence(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "deadletter.db"))
    file_path = tmp_path / "broken.json"
    file_path.write_text("{}", encoding="utf-8")

    job_id = store.enqueue_file_job(str(file_path), {}, priority_score=0.4, risk_label="medium")
    dl_id = store.add_dead_letter(
        job_id=job_id,
        reason="timeout",
        snapshot={"job_id": job_id, "source_ref": str(file_path)},
    )

    assert dl_id > 0
    assert store.get_dead_letter_count() == 1


def test_dead_letter_list_and_requeue(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "deadletter_requeue.db"))
    file_path = tmp_path / "err.json"
    file_path.write_text("{}", encoding="utf-8")

    job_id = store.enqueue_file_job(str(file_path), {}, priority_score=0.3, risk_label="low")
    claimed = store.claim_next_job()
    assert claimed is not None and int(claimed["id"]) == job_id
    store.fail_or_retry_job(job_id, "boom")

    dl_id = store.add_dead_letter(job_id, "boom", {"job_id": job_id, "source_ref": str(file_path)})
    items = store.list_dead_letters(limit=5)
    assert items and items[0]["id"] == dl_id

    requeued_job_id = store.requeue_dead_letter(dl_id, note="manual retry")
    assert requeued_job_id == job_id

    stats = store.get_job_stats()
    assert stats["pending"] == 1
