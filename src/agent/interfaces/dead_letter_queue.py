"""CLI to inspect and requeue dead-letter jobs."""

from __future__ import annotations

import argparse

from agent.storage import AuditStore


def _cmd_list(limit: int) -> None:
    store = AuditStore()
    items = store.list_dead_letters(limit=limit)
    if not items:
        print("No hay dead-letters.")
        return

    for item in items:
        print(f"- dl#{item['id']} job#{item['job_id']} at={item['created_at']}")
        print(f"  src: {item['source_ref']}")
        print(f"  reason: {item['reason']}")


def _cmd_requeue(dead_letter_id: int, note: str) -> None:
    store = AuditStore()
    job_id = store.requeue_dead_letter(dead_letter_id=dead_letter_id, note=note)
    print(f"Dead-letter #{dead_letter_id} reencolado como job #{job_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Nodaris dead-letter queue")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List dead-letter records")
    p_list.add_argument("--limit", type=int, default=25)

    p_requeue = sub.add_parser("requeue", help="Requeue a dead-letter record")
    p_requeue.add_argument("--dead-letter-id", type=int, required=True)
    p_requeue.add_argument("--note", default="")

    args = parser.parse_args()

    if args.command == "list":
        _cmd_list(limit=args.limit)
    elif args.command == "requeue":
        _cmd_requeue(dead_letter_id=args.dead_letter_id, note=args.note)


if __name__ == "__main__":
    main()
