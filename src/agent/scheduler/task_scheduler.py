"""Simple autonomous scheduler for Nodaris discovery."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agent.config import Config
from agent.nodes.discovery import discovery_node

logger = logging.getLogger("nodaris.scheduler")


def _notify_admin_sync(message: str) -> None:
    """Send an HTML Telegram message to TELEGRAM_ADMIN_CHAT_ID (sync). Silent if not configured."""
    admin_chat_id = Config.TELEGRAM_ADMIN_CHAT_ID
    bot_token = Config.TELEGRAM_BOT_TOKEN
    if not admin_chat_id or not bot_token:
        return
    try:
        import httpx
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        with httpx.Client(timeout=10) as client:
            client.post(url, json={
                "chat_id": admin_chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
    except Exception as exc:
        logger.warning("Telegram scheduler notification failed: %s", exc)


def _risk_icon(risk: str) -> str:
    """Return a colored circle icon for a risk label."""
    if risk == "high":
        return "🔴"
    if risk == "medium":
        return "🟡"
    return "🟢"


def _build_discovery_message(discovered: list) -> str:
    """Build the discovery notification message listing new inbox files."""
    lines = [f"📥 <b>{len(discovered)} archivo(s) nuevo(s) detectado(s) en inbox</b>", ""]
    for job in discovered[:10]:
        fname = Path(str(job.get("file_path", ""))).name
        risk = str(job.get("risk_label", "?"))
        lines.append(f"{_risk_icon(risk)} {fname} — riesgo: <b>{risk}</b>")
    if len(discovered) > 10:
        lines.append(f"…y {len(discovered) - 10} más")
    lines.append("")
    lines.append("<i>El agente procesará los jobs automáticamente.</i>")
    return "\n".join(lines)


def run_scheduler_loop() -> None:
    """Run discovery periodically to enqueue new jobs."""
    if not Config.AUTONOMY_ENABLED:
        return

    interval = max(30, int(Config.AUTONOMY_SCHEDULER_INTERVAL_SEC))

    while True:
        result = discovery_node({})

        discovered = result.get("discovered_jobs") or []
        if discovered:
            _notify_admin_sync(_build_discovery_message(discovered))
            logger.info("Discovery notification sent: %d new jobs", len(discovered))

        time.sleep(interval)


if __name__ == "__main__":
    run_scheduler_loop()
