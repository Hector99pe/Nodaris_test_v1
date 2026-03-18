"""CLI to manage jobs pending manual review."""

from __future__ import annotations

import argparse

from agent.storage import AuditStore


def _cmd_list(limit: int) -> None:
    store = AuditStore()
    jobs = store.list_review_jobs(limit=limit)
    if not jobs:
        return

    for item in jobs:
        if item.get("reason"):
            pass


def _cmd_decide(job_id: int, decision: str, note: str) -> None:
    store = AuditStore()
    store.review_decide(job_id=job_id, decision=decision, note=note)


def main() -> None:
    """Manage review queue (list, decide, resolve jobs)."""
    parser = argparse.ArgumentParser(description="Manage Nodaris review queue")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List jobs requiring review")
    p_list.add_argument("--limit", type=int, default=25)

    p_decide = sub.add_parser("decide", help="Approve, reject or requeue a review job")
    p_decide.add_argument("--job-id", type=int, required=True)
    p_decide.add_argument("--decision", choices=["approve", "reject", "requeue"], required=True)
    p_decide.add_argument("--note", default="")

    args = parser.parse_args()

    if args.command == "list":
        _cmd_list(limit=args.limit)
    elif args.command == "decide":
        _cmd_decide(job_id=args.job_id, decision=args.decision, note=args.note)


if __name__ == "__main__":
    main()
