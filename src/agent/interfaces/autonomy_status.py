"""CLI helper to inspect autonomous queue status."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent.storage import AuditStore


def _short_path(path_value: str, max_len: int = 72) -> str:
    text = str(path_value)
    if len(text) <= max_len:
        return text
    return f"...{text[-(max_len - 3):]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Show Nodaris autonomous queue status")
    parser.add_argument("--limit", type=int, default=10, help="recent jobs to display")
    args = parser.parse_args()

    store = AuditStore()
    stats = store.get_job_stats()
    dead_letters = store.get_dead_letter_count()
    jobs = store.list_recent_jobs(limit=args.limit)

    print("== Nodaris Autonomous Queue ==")
    print(f"DB: {Path(store.db_path).resolve()}")
    print(
        f"Total={stats['total']} | pending={stats['pending']} | running={stats['running']} "
        f"| completed={stats['completed']} | review_required={stats['review_required']} "
        f"| approved={stats['approved']} | rejected={stats['rejected']} | failed={stats['failed']} "
        f"| dead_letter={dead_letters}"
    )

    if not jobs:
        print("No hay jobs registrados.")
        return

    print("\nRecent jobs:")
    for item in jobs:
        err = item.get("error_message") or ""
        err_short = err[:80] if err else ""
        print(
            f"- #{item['id']} [{item['status']}] risk={item['risk_label']} "
            f"priority={item['priority_score']:.2f} attempts={item['attempt_count']}/{item['max_attempts']} "
            f"src={_short_path(item['source_ref'])}"
        )
        if err_short:
            print(f"  error: {err_short}")


if __name__ == "__main__":
    main()
