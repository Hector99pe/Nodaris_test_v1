"""Single-command health check for the Nodaris autonomous pipeline.

Usage:
    python -m agent.interfaces.health_check
    python -m agent.interfaces.health_check --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from agent.config import Config
from agent.resilience import get_llm_circuit_breaker_snapshot
from agent.storage import AuditStore

# ── Result levels ─────────────────────────────────────────────────────────────
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_ICONS = {PASS: "[OK  ]", WARN: "[WARN]", FAIL: "[FAIL]"}
_LLM_BREAKER_COMPONENT = "llm.circuit_breaker"


def _result(level: str, component: str, message: str) -> dict[str, str]:
    return {"level": level, "component": component, "message": message}


# ── Individual checks ─────────────────────────────────────────────────────────

def _check_openai() -> dict[str, str]:
    key = Config.OPENAI_API_KEY
    if not key:
        return _result(FAIL, "openai", "OPENAI_API_KEY no configurada")
    masked = f"{key[:8]}…{key[-4:]}" if len(key) > 12 else "***"
    return _result(PASS, "openai", f"API key presente ({masked}) | modelo={Config.OPENAI_MODEL}")


def _check_telegram() -> dict[str, str]:
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        return _result(WARN, "telegram", "TELEGRAM_BOT_TOKEN no configurada (bot desactivado)")
    masked = f"{token[:10]}…"
    return _result(PASS, "telegram", f"Token presente ({masked})")


def _check_langsmith() -> dict[str, str]:
    if Config.LANGSMITH_TRACING:
        key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
        if not key:
            return _result(WARN, "langsmith", "LANGSMITH_TRACING=true pero LANGCHAIN_API_KEY ausente")
        return _result(PASS, "langsmith", "Tracing habilitado con API key")
    return _result(PASS, "langsmith", "Tracing desactivado")


def _check_autonomy_config() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    # Autonomous mode flag
    level = PASS if Config.AUTONOMY_ENABLED else WARN
    msg = "AUTONOMY_ENABLED=true" if Config.AUTONOMY_ENABLED else "AUTONOMY_ENABLED=false (modo manual)"
    results.append(_result(level, "autonomy.enabled", msg))

    # Inbox directory
    inbox = Path(Config.AUTONOMY_INBOX_PATH)
    if inbox.exists():
        file_count = sum(1 for f in inbox.iterdir() if f.is_file())
        results.append(_result(PASS, "autonomy.inbox", f"Directorio existe | archivos={file_count}"))
    else:
        results.append(_result(WARN, "autonomy.inbox", f"Inbox no existe aún: {inbox}"))

    # Key thresholds
    results.append(_result(
        PASS,
        "autonomy.thresholds",
        f"timeout={Config.AUTONOMY_JOB_TIMEOUT_SEC}s | "
        f"retries={Config.AUTONOMY_MAX_JOB_RETRIES} | "
        f"review_confidence={Config.AUTONOMY_REVIEW_CONFIDENCE_THRESHOLD} | "
        f"high_risk_review={Config.AUTONOMY_REQUIRE_REVIEW_ON_HIGH_RISK}",
    ))

    # Learning memory
    level = PASS if Config.LEARNING_MEMORY_ENABLED else WARN
    results.append(_result(
        level,
        "autonomy.learning",
        f"LEARNING_MEMORY_ENABLED={Config.LEARNING_MEMORY_ENABLED} | "
        f"top_tools={Config.LEARNING_MEMORY_TOP_TOOLS}",
    ))

    results.append(_result(
        PASS,
        "autonomy.llm_breaker_config",
        f"failure_threshold={Config.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD} | "
        f"reset={Config.LLM_CIRCUIT_BREAKER_RESET_SEC}s | "
        f"retries={Config.LLM_CIRCUIT_BREAKER_MAX_RETRIES} | "
        f"base_delay={Config.LLM_CIRCUIT_BREAKER_BASE_DELAY_SEC}s",
    ))

    return results


def _check_llm_circuit_breaker() -> dict[str, str]:
    snapshot = get_llm_circuit_breaker_snapshot()
    state = str(snapshot.get("state", "closed"))
    failures = int(snapshot.get("consecutive_failures", 0) or 0)
    retry_after = float(snapshot.get("retry_after_sec", 0.0) or 0.0)
    last_error = str(snapshot.get("last_error", "") or "")

    if state == "open":
        detail = f"state=open | failures={failures} | retry_after={retry_after:.1f}s"
        if last_error:
            detail += f" | last_error={last_error[:120]}"
        return _result(FAIL, _LLM_BREAKER_COMPONENT, detail)

    if state == "half_open":
        return _result(
            WARN,
            _LLM_BREAKER_COMPONENT,
            f"state=half_open | failures={failures} | recovery probe in progress",
        )

    level = PASS if failures == 0 else WARN
    return _result(level, _LLM_BREAKER_COMPONENT, f"state=closed | failures={failures}")


def _check_db() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    db_path = Path(Config.AUDIT_DB_PATH)

    if not db_path.exists():
        results.append(_result(WARN, "db.file", f"Base de datos no existe aún: {db_path}"))
        return results

    size_kb = db_path.stat().st_size // 1024
    results.append(_result(PASS, "db.file", f"{db_path} ({size_kb} KB)"))

    try:
        store = AuditStore()
        stats = store.get_job_stats()
        dl_count = store.get_dead_letter_count()
        review_jobs = store.list_review_jobs(limit=5)

        # Queue stats
        pending = stats.get("pending", 0)
        running = stats.get("running", 0)
        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)

        queue_level = PASS
        if pending > 100:
            queue_level = WARN
        if running > Config.AUTONOMY_CONSUMER_BATCH_SIZE * 2:
            queue_level = WARN

        results.append(_result(
            queue_level,
            "db.queue",
            f"pending={pending} | running={running} | completed={completed} | "
            f"failed={failed} | review={stats.get('review_required', 0)} | "
            f"approved={stats.get('approved', 0)} | rejected={stats.get('rejected', 0)}",
        ))

        # Dead-letter
        dl_level = PASS if dl_count == 0 else WARN
        if dl_count > Config.AUTONOMY_DEADLETTER_MAX_ITEMS * 0.8:
            dl_level = FAIL
        results.append(_result(
            dl_level,
            "db.dead_letter",
            f"dead_letter={dl_count} / max={Config.AUTONOMY_DEADLETTER_MAX_ITEMS}",
        ))

        # Review backlog
        review_level = PASS
        total_review = stats.get("review_required", 0)
        if total_review > 20:
            review_level = WARN
        if total_review > 100:
            review_level = FAIL
        results.append(_result(
            review_level,
            "db.review_backlog",
            f"jobs en review_required={total_review}"
            + (f" — primeros {len(review_jobs)} IDs: {[j['id'] for j in review_jobs]}" if review_jobs else ""),
        ))

    except Exception as exc:  # noqa: BLE001
        results.append(_result(FAIL, "db.query", f"Error al consultar DB: {exc}"))

    return results


_PROCESS_KEYWORDS: dict[str, list[str]] = {
    "scheduler": ["autonomy_scheduler", "queue_scheduler"],
    "consumer": ["autonomy_consumer", "queue_consumer"],
}


def _scan_process_pids(psutil: Any) -> dict[str, list[int]]:
    """Return PIDs grouped by role for known Nodaris daemon patterns."""
    found: dict[str, list[int]] = {"scheduler": [], "consumer": []}
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
        except Exception:  # noqa: BLE001
            continue
        for role, patterns in _PROCESS_KEYWORDS.items():
            if any(p in cmdline for p in patterns):
                found[role].append(proc.info["pid"])
    return found


def _role_result(role: str, pids: list[int]) -> dict[str, str]:
    if pids:
        return _result(PASS, f"processes.{role}", f"Activo (PIDs: {pids})")
    level = WARN if Config.AUTONOMY_ENABLED else PASS
    suffix = " — ¿está corriendo el daemon?" if Config.AUTONOMY_ENABLED else " (autonomy desactivada)"
    return _result(level, f"processes.{role}", f"No detectado{suffix}")


def _check_processes() -> list[dict[str, str]]:
    """Detect scheduler/consumer processes via psutil if available."""
    try:
        import psutil  # type: ignore[import]
    except ImportError:
        return [_result(
            WARN,
            "processes",
            "psutil no instalado — no se puede verificar procesos activos "
            "(pip install psutil para habilitar)",
        )]

    found = _scan_process_pids(psutil)
    return [_role_result(role, pids) for role, pids in found.items()]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_health_check() -> list[dict[str, str]]:
    """Run all checks and return the list of result dicts."""
    checks: list[dict[str, str]] = []
    checks.append(_check_openai())
    checks.append(_check_telegram())
    checks.append(_check_langsmith())
    checks.extend(_check_autonomy_config())
    checks.append(_check_llm_circuit_breaker())
    checks.extend(_check_db())
    checks.extend(_check_processes())
    return checks


def _overall(checks: list[dict[str, str]]) -> str:
    levels = {c["level"] for c in checks}
    if FAIL in levels:
        return FAIL
    if WARN in levels:
        return WARN
    return PASS


def main() -> None:
    parser = argparse.ArgumentParser(description="Nodaris Health Check")
    parser.add_argument("--json", action="store_true", help="Output en formato JSON")
    args = parser.parse_args()

    checks = run_health_check()
    overall = _overall(checks)

    if args.json:
        print(json.dumps({"overall": overall, "checks": checks}, indent=2, ensure_ascii=False))
        sys.exit(0 if overall == PASS else 1)

    # Human-readable output
    print("=" * 60)
    print("  Nodaris — Health Check")
    print(f"  Estado global: {overall}")
    print("=" * 60)

    for chk in checks:
        icon = _ICONS.get(chk["level"], "[??  ]")
        print(f"  {icon} {chk['component']}")
        print(f"           {chk['message']}")

    print("=" * 60)

    # Summary line
    totals: dict[str, int] = {PASS: 0, WARN: 0, FAIL: 0}
    for chk in checks:
        totals[chk["level"]] = totals.get(chk["level"], 0) + 1
    print(
        f"  Resumen: {totals[PASS]} OK | {totals[WARN]} WARN | {totals[FAIL]} FAIL"
    )
    print("=" * 60)

    sys.exit(0 if overall == PASS else 1)


if __name__ == "__main__":
    main()
