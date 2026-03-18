"""CLI helper to inspect autonomous queue status."""

from __future__ import annotations

import argparse

from agent.storage import AuditStore


def _short_path(path_value: str, max_len: int = 72) -> str:
    text = str(path_value)
    if len(text) <= max_len:
        return text
    return f"...{text[-(max_len - 3):]}"


def main() -> None:
    """Display recent jobs and stats from autonomous queue."""
    parser = argparse.ArgumentParser(description="Show Nodaris autonomous queue status")
    parser.add_argument("--limit", type=int, default=10, help="recent jobs to display")
    args = parser.parse_args()

    store = AuditStore()
    store.get_job_stats()
    store.get_dead_letter_count()
    jobs = store.list_recent_jobs(limit=args.limit)


    if not jobs:
        return

    for item in jobs:
        err = item.get("error_message") or ""
        err_short = err[:80] if err else ""
        if err_short:
            pass


if __name__ == "__main__":
    main()
