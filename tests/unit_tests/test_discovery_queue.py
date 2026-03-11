from pathlib import Path

from agent.nodes.discovery import discovery_node
from agent.nodes.risk_scoring import score_file_risk
from agent.storage.audit_store import AuditStore


def test_discovery_enqueues_supported_files(monkeypatch, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "a_exam.json").write_text("{}", encoding="utf-8")
    (inbox / "b_exam.csv").write_text("dni,nota\n123,15", encoding="utf-8")
    (inbox / "notes.txt").write_text("ignore", encoding="utf-8")

    db_path = tmp_path / "audits.db"
    monkeypatch.setattr("agent.nodes.discovery.Config.AUTONOMY_INBOX_PATH", str(inbox))
    monkeypatch.setattr("agent.nodes.discovery.AuditStore", lambda: AuditStore(str(db_path)))

    result = discovery_node({})

    assert result["status"] == "discovered"
    assert len(result["discovered_jobs"]) == 2


def test_claim_next_job_prioritizes_higher_risk(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "priority.db"))
    low = tmp_path / "low.json"
    high = tmp_path / "exam_anomalia_critica.json"
    low.write_text("{}", encoding="utf-8")
    high.write_text("{}", encoding="utf-8")

    store.enqueue_file_job(str(low), {}, priority_score=0.2, risk_label="low")
    store.enqueue_file_job(str(high), {}, priority_score=0.9, risk_label="high")

    claimed = store.claim_next_job()
    assert claimed is not None
    assert claimed["risk_label"] == "high"
    assert abs(float(claimed["priority_score"]) - 0.9) < 1e-9


def test_risk_scoring_flags_anomaly_fixture_as_high() -> None:
    fixture = Path("data/test_exam_anomalias.json")
    risk = score_file_risk(str(fixture))
    assert risk["risk_label"] in {"high", "medium"}
    assert risk["priority_score"] > 0.4
