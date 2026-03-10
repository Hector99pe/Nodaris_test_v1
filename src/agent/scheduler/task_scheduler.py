"""Simple autonomous scheduler for Nodaris discovery."""

from __future__ import annotations

import time

from agent.config import Config
from agent.nodes.discovery import discovery_node


def run_scheduler_loop() -> None:
    """Run discovery periodically to enqueue new jobs."""
    if not Config.AUTONOMY_ENABLED:
        print("Autonomia deshabilitada (AUTONOMY_ENABLED=false)")
        return

    interval = max(30, int(Config.AUTONOMY_SCHEDULER_INTERVAL_SEC))
    print(f"Scheduler autonomo activo cada {interval}s. Inbox: {Config.AUTONOMY_INBOX_PATH}")

    while True:
        result = discovery_node({})
        print(result.get("mensaje", "Discovery ejecutado"))
        time.sleep(interval)


if __name__ == "__main__":
    run_scheduler_loop()
