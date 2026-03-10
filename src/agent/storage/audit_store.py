"""SQLite storage for Nodaris audit artifacts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agent.config import Config


_UPDATE_JOB_STATE_SQL = """
UPDATE audit_jobs
SET status = ?, completed_at = ?, error_message = ?
WHERE id = ?
"""

_SET_JOB_SOURCE_SQL = """
UPDATE audit_jobs
SET source_ref = ?
WHERE id = ?
"""


class AuditStore:
    """Persists completed audit runs and extracted findings."""

    def __init__(self, db_path: str | None = None) -> None:
        base_path = Path(db_path or Config.AUDIT_DB_PATH)
        self.db_path = base_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    status TEXT,
                    confidence_score REAL,
                    audit_hash TEXT,
                    input_mode TEXT,
                    exam_id TEXT,
                    dni TEXT,
                    summary_json TEXT,
                    report_text TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id INTEGER NOT NULL,
                    finding_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (audit_id) REFERENCES audits(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2,
                    priority_score REAL NOT NULL DEFAULT 0,
                    risk_label TEXT NOT NULL DEFAULT 'normal',
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    confidence_score REAL,
                    anomaly_detected INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letter_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    job_id INTEGER,
                    source_ref TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL
                )
                """
            )
            try:
                conn.execute("ALTER TABLE audit_jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE audit_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 2")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE audit_jobs ADD COLUMN priority_score REAL NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE audit_jobs ADD COLUMN risk_label TEXT NOT NULL DEFAULT 'normal'")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def add_dead_letter(self, job_id: int, reason: str, snapshot: Dict[str, Any]) -> int:
        """Persist a dead-letter record for a job that cannot be auto-processed."""
        now = datetime.now(timezone.utc).isoformat()
        source_ref = str(snapshot.get("source_ref", ""))
        payload = json.dumps(snapshot, ensure_ascii=False)

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO dead_letter_jobs (created_at, job_id, source_ref, reason, snapshot_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, job_id, source_ref, reason, payload),
            )
            row_id = cur.lastrowid

            # Keep dead-letter table bounded.
            max_items = max(100, int(Config.AUTONOMY_DEADLETTER_MAX_ITEMS))
            conn.execute(
                """
                DELETE FROM dead_letter_jobs
                WHERE id NOT IN (
                    SELECT id FROM dead_letter_jobs ORDER BY id DESC LIMIT ?
                )
                """,
                (max_items,),
            )
            conn.commit()

            if row_id is None:
                raise RuntimeError("No se pudo crear registro dead-letter")
            return int(row_id)

    def get_dead_letter_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM dead_letter_jobs").fetchone()
        return int(row["total"]) if row else 0

    def list_dead_letters(self, limit: int = 25) -> list[Dict[str, Any]]:
        """List dead-letter records from most recent to oldest."""
        safe_limit = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, job_id, source_ref, reason, snapshot_json
                FROM dead_letter_jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        items: list[Dict[str, Any]] = []
        for row in rows:
            snapshot_text = str(row["snapshot_json"] or "{}")
            try:
                snapshot = json.loads(snapshot_text)
            except json.JSONDecodeError:
                snapshot = {}
            items.append(
                {
                    "id": int(row["id"]),
                    "created_at": str(row["created_at"]),
                    "job_id": int(row["job_id"]) if row["job_id"] is not None else None,
                    "source_ref": str(row["source_ref"]),
                    "reason": str(row["reason"]),
                    "snapshot": snapshot,
                }
            )
        return items

    def requeue_dead_letter(self, dead_letter_id: int, note: str = "") -> int:
        """Requeue the underlying job for a dead-letter record.

        Returns the job id that was requeued.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, job_id FROM dead_letter_jobs
                WHERE id = ?
                """,
                (dead_letter_id,),
            ).fetchone()
            if row is None or row["job_id"] is None:
                raise RuntimeError(f"Dead-letter no encontrado o sin job asociado: {dead_letter_id}")

            job_id = int(row["job_id"])
            conn.execute(
                """
                UPDATE audit_jobs
                SET status = 'pending', started_at = NULL, completed_at = NULL,
                    error_message = ?, attempt_count = 0
                WHERE id = ?
                """,
                (note or "Requeue desde dead-letter", job_id),
            )
            conn.commit()
            return job_id

    def record_learning_batch(
        self,
        mode: str,
        tool_names: List[str],
        confidence_score: float,
        anomaly_detected: bool,
    ) -> None:
        """Persist one learning record per tool used in an audit iteration."""
        if not tool_names:
            return

        now = datetime.now(timezone.utc).isoformat()
        success = 1 if confidence_score >= 0.7 else 0
        anomaly_int = 1 if anomaly_detected else 0

        rows = [
            (now, mode, tool_name, success, float(confidence_score), anomaly_int)
            for tool_name in tool_names
        ]

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO agent_memory (
                    created_at, mode, tool_name, success, confidence_score, anomaly_detected
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()

    def get_learning_profile(self, mode: str, limit: int = 20) -> Dict[str, Any]:
        """Return ranked tools from historical performance for the given mode."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    tool_name,
                    COUNT(*) AS uses,
                    SUM(success) AS successes,
                    AVG(confidence_score) AS avg_confidence,
                    SUM(anomaly_detected) AS anomalies
                FROM agent_memory
                WHERE mode = ?
                GROUP BY tool_name
                ORDER BY successes DESC, avg_confidence DESC, uses DESC
                LIMIT ?
                """,
                (mode, max(1, int(limit))),
            ).fetchall()

        ranked_tools: List[str] = []
        tool_stats: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            name = str(row["tool_name"])
            ranked_tools.append(name)
            uses = int(row["uses"] or 0)
            successes = int(row["successes"] or 0)
            success_rate = round((successes / uses), 3) if uses else 0.0
            tool_stats[name] = {
                "uses": uses,
                "successes": successes,
                "success_rate": success_rate,
                "avg_confidence": round(float(row["avg_confidence"] or 0.0), 3),
                "anomalies": int(row["anomalies"] or 0),
            }

        return {
            "mode": mode,
            "ranked_tools": ranked_tools,
            "tool_stats": tool_stats,
        }

    def enqueue_file_job(
        self,
        file_path: str,
        payload: Dict[str, Any] | None = None,
        priority_score: float = 0.0,
        risk_label: str = "normal",
    ) -> int:
        """Insert a pending file job if it does not exist yet.

        Returns job id. If duplicate exists, returns existing id.
        """
        data = payload or {}
        now = datetime.now(timezone.utc).isoformat()
        source_ref = str(Path(file_path).resolve())

        max_attempts = max(1, int(Config.AUTONOMY_MAX_JOB_RETRIES) + 1)

        with self._connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO audit_jobs (
                        created_at, status, source_type, source_ref, payload_json,
                        attempt_count, max_attempts, priority_score, risk_label
                    )
                    VALUES (?, 'pending', 'file', ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        now,
                        source_ref,
                        json.dumps(data, ensure_ascii=False),
                        max_attempts,
                        float(priority_score),
                        str(risk_label),
                    ),
                )
                row_id = cur.lastrowid
                if row_id is None:
                    raise RuntimeError("No se pudo obtener id del job insertado")
                conn.commit()
                return int(row_id)
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT id FROM audit_jobs WHERE source_ref = ?",
                    (source_ref,),
                ).fetchone()
                if row is None:
                    raise
                return int(row["id"])

    def claim_next_job(self) -> Dict[str, Any] | None:
        """Claim one pending job atomically and mark it as running."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, source_type, source_ref, payload_json
                FROM audit_jobs
                WHERE status = 'pending'
                ORDER BY priority_score DESC, created_at ASC, id ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            conn.execute(
                """
                UPDATE audit_jobs
                SET status = 'running', started_at = ?, attempt_count = attempt_count + 1
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            updated = conn.execute("SELECT changes() AS n").fetchone()
            conn.commit()
            if updated is None or int(updated["n"]) != 1:
                return None

            row2 = conn.execute(
                """
                  SELECT id, source_type, source_ref, payload_json, attempt_count, max_attempts,
                      priority_score, risk_label
                FROM audit_jobs
                WHERE id = ?
                """,
                (row["id"],),
            ).fetchone()
            if row2 is None:
                return None

            payload_text = str(row2["payload_json"])
            payload = json.loads(payload_text) if payload_text else {}
            return {
                "id": int(row2["id"]),
                "source_type": str(row2["source_type"]),
                "source_ref": str(row2["source_ref"]),
                "payload": payload,
                "attempt_count": int(row2["attempt_count"]),
                "max_attempts": int(row2["max_attempts"]),
                "priority_score": float(row2["priority_score"]),
                "risk_label": str(row2["risk_label"]),
            }

    def complete_job(self, job_id: int) -> None:
        """Mark a running job as completed."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                _UPDATE_JOB_STATE_SQL,
                ("completed", now, None, job_id),
            )
            conn.commit()

    def release_job(self, job_id: int, reason: str = "") -> None:
        """Return a running job to pending without burning a retry slot."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE audit_jobs
                SET status = 'pending', started_at = NULL,
                    attempt_count = CASE WHEN attempt_count > 0 THEN attempt_count - 1 ELSE 0 END,
                    error_message = ?
                WHERE id = ?
                """,
                (reason, job_id),
            )
            conn.commit()

    def mark_job_review_required(self, job_id: int, reason: str) -> None:
        """Mark a running job as requiring manual review."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                _UPDATE_JOB_STATE_SQL,
                ("review_required", now, reason, job_id),
            )
            conn.commit()

    def update_job_source_ref(self, job_id: int, source_ref: str) -> None:
        """Update physical file location tracked by the queue job."""
        with self._connect() as conn:
            conn.execute(_SET_JOB_SOURCE_SQL, (str(Path(source_ref).resolve()), job_id))
            conn.commit()

    def list_review_jobs(self, limit: int = 25) -> list[Dict[str, Any]]:
        """List jobs currently waiting for manual review."""
        safe_limit = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, status, source_ref, risk_label, priority_score,
                       attempt_count, max_attempts, completed_at, error_message
                FROM audit_jobs
                WHERE status = 'review_required'
                ORDER BY completed_at DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [
            {
                "id": int(row["id"]),
                "status": str(row["status"]),
                "source_ref": str(row["source_ref"]),
                "risk_label": str(row["risk_label"]),
                "priority_score": float(row["priority_score"]),
                "attempt_count": int(row["attempt_count"]),
                "max_attempts": int(row["max_attempts"]),
                "completed_at": row["completed_at"],
                "reason": row["error_message"],
            }
            for row in rows
        ]

    def review_decide(self, job_id: int, decision: str, note: str = "") -> None:
        """Apply a manual decision to a review-required job.

        Supported decisions: 'approve', 'reject', 'requeue'.
        """
        normalized = decision.strip().lower()
        now = datetime.now(timezone.utc).isoformat()
        if normalized not in {"approve", "reject", "requeue"}:
            raise ValueError("Decision invalida. Usa approve|reject|requeue")

        with self._connect() as conn:
            if normalized == "requeue":
                conn.execute(
                    """
                    UPDATE audit_jobs
                    SET status = 'pending', started_at = NULL, completed_at = NULL,
                        error_message = ?, attempt_count = 0
                    WHERE id = ?
                    """,
                    (note or "Manual requeue", job_id),
                )
            else:
                status = "approved" if normalized == "approve" else "rejected"
                conn.execute(
                    _UPDATE_JOB_STATE_SQL,
                    (status, now, note or f"Manual {status}", job_id),
                )
            conn.commit()

    def fail_or_retry_job(self, job_id: int, error_message: str) -> str:
        """Fail a job or move it back to pending depending on retry budget.

        Returns final status: 'pending' or 'failed'.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempt_count, max_attempts FROM audit_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Job no encontrado: {job_id}")

            attempts = int(row["attempt_count"])
            max_attempts = int(row["max_attempts"])
            next_status = "failed" if attempts >= max_attempts else "pending"

            conn.execute(
                _UPDATE_JOB_STATE_SQL,
                (next_status, now if next_status == "failed" else None, error_message, job_id),
            )
            conn.commit()
            return next_status

    def get_job_stats(self) -> Dict[str, int]:
        """Return counters by queue status."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM audit_jobs
                GROUP BY status
                """
            ).fetchall()

        stats: Dict[str, int] = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "review_required": 0,
            "approved": 0,
            "rejected": 0,
        }
        for row in rows:
            status = str(row["status"])
            stats[status] = int(row["total"])
        stats["total"] = sum(stats.values())
        return stats

    def list_recent_jobs(self, limit: int = 10) -> list[Dict[str, Any]]:
        """Return the most recent jobs for debugging/ops visibility."""
        safe_limit = max(1, int(limit))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, status, source_type, source_ref, attempt_count, max_attempts,
                      priority_score, risk_label, created_at, started_at, completed_at, error_message
                FROM audit_jobs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        items: list[Dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "id": int(row["id"]),
                    "status": str(row["status"]),
                    "source_type": str(row["source_type"]),
                    "source_ref": str(row["source_ref"]),
                    "attempt_count": int(row["attempt_count"]),
                    "max_attempts": int(row["max_attempts"]),
                    "priority_score": float(row["priority_score"]),
                    "risk_label": str(row["risk_label"]),
                    "created_at": row["created_at"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "error_message": row["error_message"],
                }
            )
        return items

    def save_audit(self, state: Dict[str, Any], report_text: str) -> int:
        """Persist one audit report and related findings."""
        created_at = state.get("timestamp") or datetime.now(timezone.utc).isoformat()
        exam_data = state.get("exam_data") or {}
        exam_id = ""
        if isinstance(exam_data, dict):
            exam_id = str((exam_data.get("examen") or {}).get("id", ""))

        input_mode = self._detect_input_mode(state)
        summary = {
            "mensaje": state.get("mensaje"),
            "promedio": state.get("promedio"),
            "preguntas_dificiles": state.get("preguntas_dificiles"),
            "copias_detectadas": len(state.get("copias_detectadas") or []),
            "respuestas_nr": len(state.get("respuestas_nr") or []),
            "tiempos_sospechosos": len(state.get("tiempos_sospechosos") or []),
        }

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audits (
                    created_at, status, confidence_score, audit_hash,
                    input_mode, exam_id, dni, summary_json, report_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    state.get("status"),
                    state.get("confidence_score"),
                    state.get("hash"),
                    input_mode,
                    exam_id,
                    state.get("dni"),
                    json.dumps(summary, ensure_ascii=False),
                    report_text,
                ),
            )
            row_id = cur.lastrowid
            if row_id is None:
                raise RuntimeError("No se pudo obtener el id de auditoria insertado")
            audit_id = int(row_id)

            self._insert_findings(conn, audit_id, state)
            conn.commit()
            return audit_id

    @staticmethod
    def _detect_input_mode(state: Dict[str, Any]) -> str:
        if state.get("file_path"):
            return "file"
        if state.get("exam_data") or state.get("students_data"):
            return "full_exam"
        if state.get("dni"):
            return "individual"
        return "conversational"

    @staticmethod
    def _insert_findings(conn: sqlite3.Connection, audit_id: int, state: Dict[str, Any]) -> None:
        finding_specs = [
            ("plagio", state.get("copias_detectadas") or []),
            ("abandono", state.get("respuestas_nr") or []),
            ("tiempos", state.get("tiempos_sospechosos") or []),
        ]

        now = datetime.now(timezone.utc).isoformat()
        for finding_type, payload in finding_specs:
            if not payload:
                continue
            conn.execute(
                """
                INSERT INTO findings (audit_id, finding_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (audit_id, finding_type, json.dumps(payload, ensure_ascii=False), now),
            )
