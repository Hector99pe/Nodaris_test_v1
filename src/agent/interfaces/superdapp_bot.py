"""Superdapp interface for Nodaris academic audit agent.

This integration supports two usage modes:
1) Inbound webhook events from Superdapp (optional)
2) Outbound API delivery of the assistant response to Superdapp
"""

from __future__ import annotations

import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

# Load .env BEFORE importing Config (which reads env vars at import time)
project_root = Path(__file__).resolve().parent.parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add src to path for imports if needed
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agent.config import Config
from agent.conversation import process_conversation
from agent.graph.graph import get_graph_with_memory
from agent.resilience import CircuitBreakerOpenError, format_llm_circuit_breaker_message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Nodaris Superdapp Interface", version="1.0.0")
_graph = get_graph_with_memory()


def _extract_conversation_id(payload: dict[str, Any]) -> str:
    """Extract conversation/session id from common webhook payload shapes."""
    possible_paths = [
        ("conversation_id",),
        ("chat_id",),
        ("session_id",),
        ("user_id",),
        ("conversation", "id"),
        ("chat", "id"),
        ("session", "id"),
        ("event", "conversation_id"),
        ("event", "chat_id"),
    ]

    for path in possible_paths:
        cursor: Any = payload
        found = True
        for key in path:
            if isinstance(cursor, dict) and key in cursor:
                cursor = cursor[key]
            else:
                found = False
                break
        if found and cursor:
            return str(cursor)

    return f"superdapp_{uuid.uuid4().hex[:12]}"


def _extract_message_text(payload: dict[str, Any]) -> str:
    """Extract inbound user message text from common webhook payload shapes."""
    possible_paths = [
        ("message",),
        ("text",),
        ("prompt",),
        ("input",),
        ("event", "message"),
        ("event", "text"),
        ("data", "message"),
        ("data", "text"),
        ("event", "data", "message"),
        ("event", "data", "text"),
    ]

    for path in possible_paths:
        cursor: Any = payload
        found = True
        for key in path:
            if isinstance(cursor, dict) and key in cursor:
                cursor = cursor[key]
            else:
                found = False
                break
        if found and isinstance(cursor, str) and cursor.strip():
            return cursor.strip()

    return ""


def _check_webhook_secret(request: Request, payload: dict[str, Any] | None = None) -> None:
    """Validate optional webhook secret from headers."""
    expected = Config.SUPERDAPP_WEBHOOK_SECRET
    if not expected:
        return

    provided = (
        request.headers.get("x-superdapp-secret")
        or request.headers.get("x-webhook-secret")
        or request.headers.get("x-api-secret")
        or request.query_params.get("secret")
        or request.query_params.get("webhook_secret")
    )

    if not provided and payload:
        body_secret = payload.get("secret") or payload.get("webhook_secret")
        if body_secret:
            provided = str(body_secret)

    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


async def _process_user_text(conversation_id: str, message: str) -> str:
    """Route Superdapp user message to Nodaris graph."""
    # Keep thread stable per Superdapp conversation for checkpoint persistence.
    thread_id = f"superdapp_{conversation_id}"

    auditar_match = re.match(r"^/auditar\s+(\S+)\s+(\d+)\s*$", message.strip(), flags=re.IGNORECASE)
    if auditar_match:
        dni, nota_raw = auditar_match.groups()
        nota = int(nota_raw)
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = await _graph.ainvoke({"dni": dni, "nota": nota}, config=config)
        except CircuitBreakerOpenError as exc:
            return format_llm_circuit_breaker_message(exc)

        if result.get("reporte_final"):
            return str(result["reporte_final"])
        if result.get("mensaje"):
            return str(result["mensaje"])
        return "Auditoria procesada correctamente."

    return await process_conversation(message=message, thread_id=thread_id)


async def send_superdapp_message(conversation_id: str, message: str) -> bool:
    """Send assistant response back to Superdapp through REST API."""
    api_url = Config.SUPERDAPP_API_URL.strip()
    api_key = Config.SUPERDAPP_API_KEY
    endpoint = Config.SUPERDAPP_SEND_ENDPOINT.strip() or "/messages"

    if not api_url or not api_key:
        logger.warning("Superdapp API not configured (SUPERDAPP_API_URL/SUPERDAPP_API_KEY)")
        return False

    url = f"{api_url.rstrip('/')}/{endpoint.lstrip('/')}"
    payload = {
        "conversation_id": conversation_id,
        "message": message,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Failed to deliver message to Superdapp API: %s", exc)
        return False


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health endpoint for process supervisors."""
    return {
        "ok": True,
        "service": "nodaris-superdapp",
        "webhook_path": Config.SUPERDAPP_WEBHOOK_PATH,
    }


async def superdapp_webhook(request: Request) -> dict[str, Any]:
    """Receive inbound notifications/events from Superdapp."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    _check_webhook_secret(request, payload)

    conversation_id = _extract_conversation_id(payload)
    user_message = _extract_message_text(payload)

    if not user_message:
        raise HTTPException(status_code=400, detail="No inbound message text found in payload")

    try:
        response_text = await _process_user_text(conversation_id=conversation_id, message=user_message)
    except CircuitBreakerOpenError as exc:
        response_text = format_llm_circuit_breaker_message(exc)
    except Exception as exc:
        logger.exception("Error processing Superdapp message")
        response_text = f"Error interno procesando mensaje: {str(exc)[:200]}"

    delivered = await send_superdapp_message(conversation_id=conversation_id, message=response_text)

    return {
        "ok": True,
        "conversation_id": conversation_id,
        "response": response_text,
        "delivered": delivered,
    }


app.add_api_route(
    Config.SUPERDAPP_WEBHOOK_PATH,
    superdapp_webhook,
    methods=["POST"],
)


def run_superdapp_webhook() -> None:
    """Run Superdapp webhook server.

    Webhook is optional but required if you want to receive inbound events
    (user messages, notifications, triggers) from Superdapp.
    """
    port = Config.SUPERDAPP_WEBHOOK_PORT
    path = Config.SUPERDAPP_WEBHOOK_PATH
    print("Iniciando servidor Superdapp webhook...")
    print(f"Escuchando en puerto {port} | Path: {path}")
    uvicorn.run(
        "agent.interfaces.superdapp_bot:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run_superdapp_webhook()
