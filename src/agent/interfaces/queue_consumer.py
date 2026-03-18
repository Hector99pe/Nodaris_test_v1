"""Queue consumer that executes autonomous audit jobs."""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from typing import cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig

from agent.config import Config
from agent.graph.graph import graph
from agent.resilience import CircuitBreakerOpenError, get_llm_circuit_breaker_snapshot
from agent.state import AcademicAuditState
from agent.storage import AuditStore

logger = logging.getLogger("nodaris.queue_consumer")


# ---------------------------------------------------------------------------
# Telegram notification helpers
# ---------------------------------------------------------------------------

async def _notify_admin(message: str, parse_mode: str | None = "HTML") -> None:
    """Send a Telegram message to TELEGRAM_ADMIN_CHAT_ID. Silent if not configured."""
    admin_chat_id = Config.TELEGRAM_ADMIN_CHAT_ID
    bot_token = Config.TELEGRAM_BOT_TOKEN
    if not admin_chat_id or not bot_token:
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": admin_chat_id,
            "text": message,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)


def _split_telegram_text(text: str, max_len: int = 3500) -> list[str]:
    """Split long text into Telegram-safe chunks without cutting words when possible."""
    src = str(text or "")
    if len(src) <= max_len:
        return [src]

    chunks: list[str] = []
    remaining = src
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def _notify_admin_report(report_text: str) -> None:
    """Send full report to Telegram in one or multiple messages."""
    chunks = _split_telegram_text(report_text, max_len=3500)
    total = len(chunks)
    for i, chunk in enumerate(chunks, start=1):
        header = "Reporte:\n" if i == 1 else f"Reporte (continuación {i}/{total}):\n"
        await _notify_admin(header + chunk, parse_mode=None)


def _build_reflection_alert(job_id: int, file_name: str, chunk_data: dict) -> str | None:
    """Build an intermediate finding alert from a reflection_node chunk, or None if not noteworthy."""
    anomaly = bool(chunk_data.get("anomalia_detectada"))
    confidence = chunk_data.get("confidence_score")
    if confidence is None:
        return None
    confidence = float(confidence)
    threshold = float(getattr(Config, "AUTONOMY_REVIEW_CONFIDENCE_THRESHOLD", 0.75))
    if not anomaly and confidence >= threshold:
        return None  # Clean result, no alert needed mid-stream

    lines = [f"🔎 <b>Hallazgos detectados — Job #{job_id}</b>", f"📁 {file_name}", ""]

    copias = chunk_data.get("copias_detectadas") or []
    tiempos = chunk_data.get("tiempos_sospechosos") or []
    abandonos = chunk_data.get("respuestas_nr") or []

    if copias:
        lines.append(f"📋 <b>Copias:</b> {len(copias)} par(es) sospechoso(s)")
    if tiempos:
        lines.append(f"⏰ <b>Tiempos sospechosos:</b> {len(tiempos)}")
    if abandonos:
        lines.append(f"🏃 <b>Abandonos (NR):</b> {len(abandonos)}")
    if not (copias or tiempos or abandonos):
        lines.append("⚠️ Anomalía detectada (sin detalle aún)")
    lines.append("")
    lines.append(f"📊 Confianza parcial: {confidence:.0%}")
    if confidence < threshold:
        lines.append("🔄 El agente está reevaluando (replanning)…")
    return "\n".join(lines)


def _build_findings_lines(copias: list, tiempos: list, abandonos: list) -> list[str]:
    """Build findings bullet lines for audit summary."""
    lines: list[str] = []
    if copias:
        alto = sum(1 for c in copias if str(c.get("nivel_sospecha", "")).upper() == "ALTO")
        suffix = f" ({alto} ALTO)" if alto else ""
        lines.append(f"  • Copias: {len(copias)} par(es){suffix}")
    if tiempos:
        lines.append(f"  • Tiempos sospechosos: {len(tiempos)}")
    if abandonos:
        lines.append(f"  • Abandonos (NR): {len(abandonos)}")
    return lines


def _build_completed_summary(job_id: int, file_name: str, result: dict) -> str:
    """Build the compact completion summary (not the full report)."""
    confidence = float(result.get("confidence_score") or 0.0)
    anomaly = bool(result.get("anomalia_detectada"))
    copias = result.get("copias_detectadas") or []
    tiempos = result.get("tiempos_sospechosos") or []
    abandonos = result.get("respuestas_nr") or []
    promedio = result.get("promedio")
    students_data = result.get("students_data") or []
    audit_hash = str(result.get("hash") or "")[:8]

    status_icon = "⚠️" if anomaly else "✅"
    status_text = "Anomalías detectadas" if anomaly else "Sin anomalías"

    lines = [
        f"{status_icon} <b>Auditoría completada — Job #{job_id}</b>",
        f"📁 {file_name}",
        "",
        f"📊 Confianza: <b>{confidence:.0%}</b>",
    ]
    if students_data:
        lines.append(f"👥 Estudiantes analizados: {len(students_data)}")
    if promedio is not None:
        lines.append(f"📈 Promedio: {float(promedio):.1f}")
    lines.append(f"🔍 Estado: {status_text}")
    lines.extend(_build_findings_lines(copias, tiempos, abandonos))
    if audit_hash:
        lines.append(f"🔐 Hash: <code>{audit_hash}…</code>")
    lines.append("")
    lines.append("\n<i>Reporte completo guardado en base de datos.</i>")
    return "\n".join(lines)


def _build_review_alert(job_id: int, file_name: str, reason: str) -> str:
    return (
        f"🔍 <b>Revisión manual requerida — Job #{job_id}</b>\n"
        f"📁 {file_name}\n\n"
        f"📋 Razón: {reason}\n\n"
        f"<i>Usa /stats o <code>review_queue.py list</code> para decidir.</i>"
    )


def _build_dead_letter_alert(job_id: int, file_name: str, reason: str) -> str:
    return (
        f"⚠️ <b>Job fallido → Dead Letter — #{job_id}</b>\n"
        f"📁 {file_name}\n\n"
        f"❌ Razón: {reason[:200]}\n\n"
        f"<i>Revisa con /stats o en la base de datos.</i>"
    )


def _build_batch_summary(counts: dict[str, int]) -> str:
    """Build the batch summary notification message from outcome counts."""
    parts = []
    if counts.get("completed"):
        parts.append(f"{counts['completed']} ✅ completados")
    if counts.get("review"):
        parts.append(f"{counts['review']} 🔍 en revisión")
    if counts.get("failed"):
        parts.append(f"{counts['failed']} ❌ fallidos")
    if counts.get("released"):
        parts.append(f"{counts['released']} ⏸️ liberados (circuit breaker)")
    detail = ", ".join(parts) if parts else "sin detalles"
    return f"📊 <b>Batch completado</b>\n{detail}"


# ---------------------------------------------------------------------------
# File archiving helpers
# ---------------------------------------------------------------------------

def _archive_file(file_path: str, target_dir: str) -> str | None:
    """Move a processed file into target archive directory and return new path."""
    src = Path(file_path)
    if not src.exists():
        return None
    dst_dir = Path(target_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name

    # Avoid collisions by suffixing a short token.
    if dst.exists():
        dst = dst_dir / f"{src.stem}_{uuid.uuid4().hex[:6]}{src.suffix}"

    shutil.move(str(src), str(dst))
    return str(dst)


def _should_require_review(job: dict, result: dict) -> tuple[bool, str]:
    """Return whether policy requires manual review and its reason."""
    risk_label = str(job.get("risk_label", "low"))
    confidence = float(result.get("confidence_score", 1.0) or 1.0)
    anomaly_detected = bool(result.get("anomalia_detectada"))

    if Config.AUTONOMY_REQUIRE_REVIEW_ON_HIGH_RISK and risk_label == "high":
        return True, "Policy: high risk job requires review"
    if confidence < Config.AUTONOMY_REVIEW_CONFIDENCE_THRESHOLD:
        return True, f"Policy: low confidence ({confidence:.2f})"
    if anomaly_detected and risk_label in {"medium", "high"}:
        return True, "Policy: anomaly detected on medium/high risk job"
    return False, ""


def _archive_and_update(store: AuditStore, job_id: int, file_path: str, target_dir: str) -> str:
    archived = _archive_file(file_path, target_dir)
    if archived:
        store.update_job_source_ref(job_id, archived)
        return archived
    return file_path


def _mark_failed_with_dead_letter(
    store: AuditStore,
    job_id: int,
    file_path: str,
    reason: str,
    snapshot: dict,
) -> None:
    status = store.fail_or_retry_job(job_id, error_message=reason)
    if status != "failed":
        return
    final_ref = _archive_and_update(store, job_id, file_path, Config.AUTONOMY_FAILED_PATH)
    store.add_dead_letter(job_id, reason, {**snapshot, "source_ref": final_ref})
    msg = _build_dead_letter_alert(job_id, Path(file_path).name, reason)
    _task = asyncio.ensure_future(_notify_admin(msg))
    logger.info("Admin notified about failed job %d (task=%s)", job_id, _task)


# ---------------------------------------------------------------------------
# Graph streaming + job execution
# ---------------------------------------------------------------------------

async def _run_audit_stream(
    state: dict,
    config: RunnableConfig,
    job_id: int,
    file_name: str,
) -> dict:
    """Stream the audit graph, firing intermediate notifications from reflection_node."""
    accumulated: dict = {}
    reflection_alerted = False

    async for chunk in graph.astream(cast(AcademicAuditState, state), config=config):
        # chunk is {node_name: output_dict}
        for node_name, output in chunk.items():
            if not isinstance(output, dict):
                continue
            accumulated.update(output)

            # Emit reflection alert once when the agent surfaces key findings
            if node_name == "reflection_node" and not reflection_alerted:
                alert = _build_reflection_alert(job_id, file_name, output)
                if alert:
                    _task = asyncio.ensure_future(_notify_admin(alert))
                    reflection_alerted = True
                    logger.info("Reflection alert sent for job %d (task=%s)", job_id, _task)

    return accumulated


async def consume_once() -> str | None:
    """Consume one pending job and execute audit graph.

    Returns:
        "completed" | "review" | "released" | "failed" — or None if queue was empty.
    """
    store = AuditStore()
    job = store.claim_next_job()
    if not job:
        return None

    job_id = int(job["id"])
    file_path = str(job["source_ref"])
    file_name = Path(file_path).name
    risk_label = str(job.get("risk_label") or "low")
    attempt = int(job.get("attempt_count") or 1)
    max_attempts = int(job.get("max_attempts") or 3)

    # --- Notification 1: job started ---
    _task = asyncio.ensure_future(_notify_admin(
        f"🔄 <b>Auditoría iniciada — Job #{job_id}</b>\n"
        f"📁 {file_name}\n"
        f"⚖️ Riesgo: {risk_label} | Intento: {attempt}/{max_attempts}"
    ))
    logger.info("Job %d started: %s (task=%s)", job_id, file_name, _task)

    def _snapshot() -> dict:
        return {
            "job_id": job_id,
            "source_ref": file_path,
            "risk_label": risk_label,
            "priority_score": job.get("priority_score"),
            "attempt_count": attempt,
            "max_attempts": max_attempts,
        }

    try:
        file_ext = Path(file_path).suffix.lower().lstrip(".")
        state = {
            "file_path": file_path,
            "file_type": file_ext,
            "messages": [HumanMessage(content=f"Audita automaticamente el archivo {file_name}")],
        }
        config = cast(RunnableConfig, {"configurable": {"thread_id": f"auto_job_{job_id}_{uuid.uuid4().hex[:6]}"}})

        # Stream graph — captures reflection events mid-run
        result = await asyncio.wait_for(
            _run_audit_stream(state, config, job_id, file_name),
            timeout=max(10, int(Config.AUTONOMY_JOB_TIMEOUT_SEC)),
        )

        requires_review, review_reason = _should_require_review(job, result)
        if requires_review:
            store.mark_job_review_required(job_id, reason=review_reason)
            _archive_and_update(store, job_id, file_path, Config.AUTONOMY_REVIEW_PATH)
            # --- Notification 2: review required (individual, always) ---
            _task = asyncio.ensure_future(_notify_admin(
                _build_review_alert(job_id, file_name, review_reason)
            ))
            logger.debug("Review alert task: %s", _task)
            return "review"
        else:
            store.complete_job(job_id)
            _archive_and_update(store, job_id, file_path, Config.AUTONOMY_PROCESSED_PATH)
            # --- Notification 3: completion summary ---
            _task = asyncio.ensure_future(_notify_admin(
                _build_completed_summary(job_id, file_name, result)
            ))
            logger.debug("Completion summary task: %s", _task)
            full_report = result.get("reporte_final")
            if isinstance(full_report, str) and full_report.strip():
                _report_task = asyncio.ensure_future(_notify_admin_report(full_report))
                logger.debug("Full report task: %s", _report_task)
            return "completed"
    except CircuitBreakerOpenError as exc:
        store.release_job(job_id, reason=str(exc))
        return "released"
    except asyncio.TimeoutError:
        _mark_failed_with_dead_letter(store, job_id, file_path, "timeout", _snapshot())
        return "failed"
    except Exception as exc:
        _mark_failed_with_dead_letter(store, job_id, file_path, str(exc), _snapshot())
        return "failed"


async def _run_one_batch() -> tuple[int, dict[str, int]]:
    """Process up to AUTONOMY_CONSUMER_BATCH_SIZE jobs. Returns (processed, outcome_counts)."""
    counts: dict[str, int] = {"completed": 0, "review": 0, "failed": 0, "released": 0}
    processed = 0
    for _ in range(max(1, Config.AUTONOMY_CONSUMER_BATCH_SIZE)):
        outcome = await consume_once()
        if outcome is None:
            break
        processed += 1
        counts[outcome] = counts.get(outcome, 0) + 1
    return processed, counts


async def run_consumer_loop() -> None:
    """Continuously process pending jobs from SQLite queue."""
    if not Config.AUTONOMY_ENABLED:
        return

    idle_sleep = 3

    while True:
        processed, counts = await _run_one_batch()

        if processed > 0:
            # --- Notification 4: batch summary ---
            _task = asyncio.ensure_future(_notify_admin(_build_batch_summary(counts)))
            logger.info("Batch done: %s (task=%s)", counts, _task)
        else:
            snapshot = get_llm_circuit_breaker_snapshot()
            retry_after = float(snapshot.get("retry_after_sec", 0.0) or 0.0)
            await asyncio.sleep(max(idle_sleep, retry_after))


if __name__ == "__main__":
    asyncio.run(run_consumer_loop())
