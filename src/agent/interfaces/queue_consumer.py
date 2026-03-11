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


async def _notify_admin_failed_job(job_id: int, file_path: str, reason: str) -> None:
    """Send Telegram notification to admin when a job exhausts retries."""
    admin_chat_id = Config.TELEGRAM_ADMIN_CHAT_ID
    bot_token = Config.TELEGRAM_BOT_TOKEN
    if not admin_chat_id or not bot_token:
        return

    try:
        import httpx
        file_name = Path(file_path).name
        message = (
            f"⚠️ <b>Job fallido → Dead Letter</b>\n\n"
            f"📋 Job ID: {job_id}\n"
            f"📁 Archivo: {file_name}\n"
            f"❌ Razón: {reason[:200]}\n\n"
            f"Revisa con /review o en la base de datos."
        )
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": admin_chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
        logger.info("Admin notified about failed job %d", job_id)
    except Exception as e:
        logger.warning("Failed to notify admin about job %d: %s", job_id, e)


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
    # Notify admin via Telegram about the permanently failed job
    asyncio.ensure_future(_notify_admin_failed_job(job_id, file_path, reason))


async def consume_once() -> bool:
    """Consume one pending job and execute audit graph. Returns True if processed."""
    store = AuditStore()
    job = store.claim_next_job()
    if not job:
        return False

    job_id = int(job["id"])
    file_path = str(job["source_ref"])

    def _snapshot() -> dict:
        return {
            "job_id": job_id,
            "source_ref": file_path,
            "risk_label": job.get("risk_label"),
            "priority_score": job.get("priority_score"),
            "attempt_count": job.get("attempt_count"),
            "max_attempts": job.get("max_attempts"),
        }

    try:
        file_ext = Path(file_path).suffix.lower().lstrip(".")
        state = {
            "file_path": file_path,
            "file_type": file_ext,
            "messages": [HumanMessage(content=f"Audita automaticamente el archivo {Path(file_path).name}")],
        }
        config = cast(RunnableConfig, {"configurable": {"thread_id": f"auto_job_{job_id}_{uuid.uuid4().hex[:6]}"}})
        result = await asyncio.wait_for(
            graph.ainvoke(cast(AcademicAuditState, state), config=config),
            timeout=max(10, int(Config.AUTONOMY_JOB_TIMEOUT_SEC)),
        )
        requires_review, reason = _should_require_review(job, cast(dict, result or {}))
        if requires_review:
            store.mark_job_review_required(job_id, reason=reason)
            _archive_and_update(store, job_id, file_path, Config.AUTONOMY_REVIEW_PATH)
        else:
            store.complete_job(job_id)
            _archive_and_update(store, job_id, file_path, Config.AUTONOMY_PROCESSED_PATH)
        return True
    except CircuitBreakerOpenError as exc:
        store.release_job(job_id, reason=str(exc))
        return False
    except asyncio.TimeoutError:
        _mark_failed_with_dead_letter(store, job_id, file_path, "timeout", _snapshot())
        return True
    except Exception as exc:
        _mark_failed_with_dead_letter(store, job_id, file_path, str(exc), _snapshot())
        return True


async def run_consumer_loop() -> None:
    """Continuously process pending jobs from SQLite queue."""
    if not Config.AUTONOMY_ENABLED:
        print("Autonomia deshabilitada (AUTONOMY_ENABLED=false)")
        return

    idle_sleep = 3
    print("Queue consumer autonomo activo")

    while True:
        processed = 0
        for _ in range(max(1, Config.AUTONOMY_CONSUMER_BATCH_SIZE)):
            if not await consume_once():
                break
            processed += 1

        if processed == 0:
            snapshot = get_llm_circuit_breaker_snapshot()
            retry_after = float(snapshot.get("retry_after_sec", 0.0) or 0.0)
            await asyncio.sleep(max(idle_sleep, retry_after))


if __name__ == "__main__":
    asyncio.run(run_consumer_loop())
