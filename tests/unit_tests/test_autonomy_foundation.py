import json
from pathlib import Path

from agent.graph.graph import route_after_reasoner
from agent.nodes.planner import planner_node
from agent.storage.audit_store import AuditStore
from agent.tools import file_parser


def test_clarification_tool_is_non_blocking_by_default(monkeypatch) -> None:
    monkeypatch.setattr(file_parser.Config, "ALLOW_HUMAN_INTERRUPT", False)

    def _fail_if_called(_payload):
        raise AssertionError("interrupt should not be called in autonomous mode")

    monkeypatch.setattr(file_parser, "interrupt", _fail_if_called)

    raw = file_parser.tool_solicitar_clarificacion.invoke(
        {"pregunta": "Que columna es DNI?", "opciones": "dni|codigo|id"}
    )
    payload = json.loads(raw)

    assert payload["tipo"] == "clarificacion_no_bloqueante"
    assert payload["fallback_aplicado"] == "dni"


def test_audit_store_persists_audit_and_findings(tmp_path: Path) -> None:
    db_path = tmp_path / "audits.db"
    store = AuditStore(str(db_path))

    state = {
        "status": "completed",
        "confidence_score": 0.91,
        "hash": "abc123",
        "exam_data": {"examen": {"id": "EX-001"}},
        "copias_detectadas": [{"estudiante1": "A", "estudiante2": "B"}],
        "respuestas_nr": ["12345678"],
        "tiempos_sospechosos": [],
        "mensaje": "ok",
    }

    audit_id = store.save_audit(state, "reporte")

    assert audit_id > 0
    assert db_path.exists()


def test_route_after_reasoner_stops_at_max_iterations(monkeypatch) -> None:
    monkeypatch.setattr("agent.graph.graph.Config.MAX_AGENT_ITERATIONS", 2)
    result = route_after_reasoner({"iteration_count": 2, "messages": []})
    assert result == "__end__"


def test_job_retries_then_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agent.storage.audit_store.Config.AUTONOMY_MAX_JOB_RETRIES", 1)
    store = AuditStore(str(tmp_path / "queue.db"))

    job_id = store.enqueue_file_job(str(tmp_path / "exam.json"), {})
    job = store.claim_next_job()
    assert job is not None and job["id"] == job_id

    status_1 = store.fail_or_retry_job(job_id, "error 1")
    assert status_1 == "pending"

    job = store.claim_next_job()
    assert job is not None and job["id"] == job_id

    status_2 = store.fail_or_retry_job(job_id, "error 2")
    assert status_2 == "failed"


def test_job_stats_and_recent_jobs(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "stats.db"))
    job_a = store.enqueue_file_job(str(tmp_path / "a.json"), {})
    job_b = store.enqueue_file_job(str(tmp_path / "b.json"), {})

    claimed = store.claim_next_job()
    assert claimed is not None
    store.complete_job(int(claimed["id"]))

    # Leave one pending to verify counters.
    assert job_a > 0 and job_b > 0

    stats = store.get_job_stats()
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["total"] == 2

    recent = store.list_recent_jobs(limit=2)
    assert len(recent) == 2


def test_learning_profile_prioritizes_successful_tools(tmp_path: Path) -> None:
    store = AuditStore(str(tmp_path / "learning.db"))
    store.record_learning_batch(
        mode="full_exam",
        tool_names=["detectar_plagio", "calcular_estadisticas"],
        confidence_score=0.9,
        anomaly_detected=True,
    )
    store.record_learning_batch(
        mode="full_exam",
        tool_names=["calcular_estadisticas"],
        confidence_score=0.4,
        anomaly_detected=False,
    )

    profile = store.get_learning_profile("full_exam")
    assert profile["ranked_tools"][0] == "detectar_plagio"


def test_planner_uses_learning_priority(monkeypatch) -> None:
    class _FakeStore:
        def get_learning_profile(self, mode: str):
            assert mode == "full_exam"
            return {
                "mode": mode,
                "ranked_tools": ["detectar_plagio", "analizar_tiempos"],
                "tool_stats": {},
            }

    monkeypatch.setattr("agent.nodes.planner.Config.LEARNING_MEMORY_ENABLED", True)
    monkeypatch.setattr("agent.nodes.planner.AuditStore", lambda: _FakeStore())

    state = {
        "exam_data": {"preguntas": [{"id": 1}]},
        "students_data": [
            {"dni": "1", "respuestas": ["A"], "tiempo_total": 10},
            {"dni": "2", "respuestas": ["A"], "tiempo_total": 10},
        ],
    }

    out = planner_node(state)
    plan = out.get("plan", "")
    assert "Prioridad por histórico" in plan
    assert "detectar_plagio" in plan
