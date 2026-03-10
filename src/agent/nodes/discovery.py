"""Discovery node for autonomous audit ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from langsmith import traceable

from agent.config import Config
from agent.nodes.risk_scoring import score_file_risk
from agent.storage import AuditStore

_SUPPORTED = {".json", ".xlsx", ".xls", ".csv", ".pdf"}


@traceable(name="discoveryNode")
def discovery_node(state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Discover new input files and enqueue autonomous audit jobs."""
    _ = state
    inbox = Path(Config.AUTONOMY_INBOX_PATH)
    inbox.mkdir(parents=True, exist_ok=True)

    store = AuditStore()
    enqueued: List[Dict[str, Any]] = []

    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED:
            continue
        risk = score_file_risk(str(path))
        payload = {
            "file_type": path.suffix.lower().lstrip("."),
            "risk_reasons": risk.get("reasons", []),
        }
        job_id = store.enqueue_file_job(
            str(path),
            payload,
            priority_score=float(risk.get("priority_score", 0.0)),
            risk_label=str(risk.get("risk_label", "low")),
        )
        enqueued.append(
            {
                "job_id": job_id,
                "file_path": str(path),
                "priority_score": risk.get("priority_score", 0.0),
                "risk_label": risk.get("risk_label", "low"),
            }
        )

    return {
        "status": "discovered",
        "mensaje": f"Discovery completo: {len(enqueued)} jobs encolados",
        "discovered_jobs": enqueued,
    }
