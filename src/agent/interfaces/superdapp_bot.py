"""Superdapp interface for Nodaris academic audit agent.

This integration supports two usage modes:
1) Inbound webhook events from Superdapp (optional)
2) Outbound API delivery of the assistant response to Superdapp
"""

from __future__ import annotations

import logging
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote_plus

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


def _norm_key(key: str) -> str:
    """Normalize keys to compare snake_case, kebab-case and camelCase equally."""
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _find_nested_value(payload: Any, wanted_keys: set[str]) -> Any:
    """Depth-first search for first value whose key matches wanted keys."""
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            # Prefer direct key matches in this level.
            for k, v in current.items():
                if _norm_key(str(k)) in wanted_keys and v not in (None, ""):
                    return v
            # Keep searching nested structures.
            for v in current.values():
                if isinstance(v, (dict, list, tuple)):
                    stack.append(v)
        elif isinstance(current, (list, tuple)):
            for item in current:
                if isinstance(item, (dict, list, tuple)):
                    stack.append(item)
    return None


def _stringify_message_candidate(candidate: Any) -> str:
    """Convert common payload message shapes into plain text."""
    if isinstance(candidate, str):
        text = candidate.strip()

        # Superdapp may send a compact envelope as JSON string:
        # {"m":"%7B%22body%22%3A%22Hola%22%7D","t":"chat"}
        try:
            raw_obj = json.loads(text)
            if isinstance(raw_obj, dict):
                packed = raw_obj.get("m")
                if isinstance(packed, str) and packed.strip():
                    decoded = unquote_plus(packed)
                    try:
                        inner = json.loads(decoded)
                        if isinstance(inner, dict):
                            inner_text = _stringify_message_candidate(inner)
                            if inner_text:
                                return inner_text
                    except Exception:
                        if decoded.strip():
                            return decoded.strip()
        except Exception:
            pass

        # If body itself is URL-encoded JSON/string, decode it.
        if "%" in text:
            decoded = unquote_plus(text)
            if decoded and decoded != text:
                try:
                    decoded_obj = json.loads(decoded)
                    decoded_text = _stringify_message_candidate(decoded_obj)
                    if decoded_text:
                        return decoded_text
                except Exception:
                    if decoded.strip():
                        return decoded.strip()

        return text
    if isinstance(candidate, (int, float)):
        return str(candidate)
    if isinstance(candidate, dict):
        for key in (
            "text",
            "message",
            "content",
            "body",
            "prompt",
            "input",
            "query",
            "searchTerm",
            "search_term",
            "plainText",
            "plain_text",
            "value",
            "raw",
            "markdown",
            "caption",
            "title",
        ):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = _find_nested_value(candidate, {
            "text",
            "message",
            "content",
            "messagetext",
            "userinput",
            "prompt",
            "input",
            "query",
            "searchterm",
            "plaintext",
            "value",
            "raw",
            "markdown",
            "caption",
            "title",
        })
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _extract_conversation_id(payload: dict[str, Any]) -> str:
    """Extract conversation/session id from common webhook payload shapes."""
    possible_paths = [
        ("conversation_id",),
        ("conversationId",),
        ("chat_id",),
        ("chatId",),
        ("session_id",),
        ("sessionId",),
        ("user_id",),
        ("userId",),
        ("thread_id",),
        ("threadId",),
        ("conversation", "id"),
        ("chat", "id"),
        ("session", "id"),
        ("data", "conversation_id"),
        ("data", "conversationId"),
        ("event", "conversationId"),
        ("event", "conversation_id"),
        ("event", "chat_id"),
        ("event", "chatId"),
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

    nested = _find_nested_value(payload, {
        "conversationid",
        "chatid",
        "sessionid",
        "userid",
        "threadid",
    })
    if nested not in (None, ""):
        return str(nested)

    return f"superdapp_{uuid.uuid4().hex[:12]}"


def _extract_message_text(payload: dict[str, Any]) -> str:
    """Extract inbound user message text from common webhook payload shapes."""
    possible_paths = [
        ("message",),
        ("text",),
        ("content",),
        ("body",),
        ("searchTerm",),
        ("search_term",),
        ("prompt",),
        ("input",),
        ("query",),
        ("body", "content"),
        ("body", "plainText"),
        ("body", "plain_text"),
        ("body", "value"),
        ("body", "raw"),
        ("body", "markdown"),
        ("body", "message"),
        ("body", "text"),
        ("data", "content"),
        ("event", "content"),
        ("event", "query"),
        ("event", "message"),
        ("event", "text"),
        ("data", "message"),
        ("data", "text"),
        ("event", "data", "message"),
        ("event", "data", "text"),
        ("event", "payload", "message"),
        ("event", "payload", "text"),
        ("payload", "message"),
        ("payload", "text"),
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
        if found:
            text = _stringify_message_candidate(cursor)
            if text:
                return text

    nested = _find_nested_value(payload, {
        "message",
        "messagetext",
        "text",
        "content",
        "userinput",
        "prompt",
        "input",
        "query",
        "searchterm",
        "plaintext",
        "value",
        "raw",
        "markdown",
        "caption",
        "title",
    })
    nested_text = _stringify_message_candidate(nested)
    if nested_text:
        return nested_text

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


async def send_superdapp_message(
    conversation_id: str,
    message: str,
    routing_context: dict[str, Any] | None = None,
) -> bool:
    """Send assistant response back to Superdapp through REST API."""
    api_url = Config.SUPERDAPP_API_URL.strip()
    api_key = Config.SUPERDAPP_API_KEY
    endpoint = Config.SUPERDAPP_SEND_ENDPOINT.strip() or "/messages"

    if not api_url or not api_key:
        logger.warning("Superdapp API not configured (SUPERDAPP_API_URL/SUPERDAPP_API_KEY)")
        return False

    url = f"{api_url.rstrip('/')}/{endpoint.lstrip('/')}"
    compact_body = quote(json.dumps({"body": message}, ensure_ascii=False), safe="")
    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "conversationId": conversation_id,
        "chatId": conversation_id,
        "message": message,
        "text": message,
        "response": message,
        "reply": message,
        "body": message,
        "m": compact_body,
        "t": "chat",
    }
    if routing_context:
        for key in (
            "chatId",
            "roomId",
            "memberId",
            "roomParticipantId",
            "senderId",
            "userId",
            "id",
            "type",
            "owner",
        ):
            value = routing_context.get(key)
            if value not in (None, ""):
                payload[key] = value

        # Some APIs expect target identifiers in a nested envelope.
        payload["data"] = {
            k: payload[k]
            for k in (
                "chatId",
                "roomId",
                "memberId",
                "roomParticipantId",
                "senderId",
                "userId",
            )
            if k in payload
        }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        if Config.SUPERDAPP_DEBUG_WEBHOOK:
            logger.info("Superdapp async delivery target url=%s", url)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            if Config.SUPERDAPP_DEBUG_WEBHOOK:
                preview = response.text[:300].replace("\n", " ")
                logger.info(
                    "Superdapp async delivery response status=%s body=%r",
                    response.status_code,
                    preview,
                )
            response.raise_for_status()

            # Some APIs return 200 but indicate failure in JSON payload.
            try:
                data = response.json()
                if isinstance(data, dict):
                    lowered_keys = {str(k).lower(): v for k, v in data.items()}
                    if lowered_keys.get("ok") is False or lowered_keys.get("success") is False:
                        logger.warning("Superdapp API returned logical failure payload: %s", data)
                        return False
            except Exception:
                pass
        return True
    except Exception as exc:
        logger.error("Failed to deliver message to Superdapp API (url=%s): %s", url, exc)
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

    if Config.SUPERDAPP_DEBUG_WEBHOOK:
        payload_keys = sorted(payload.keys()) if isinstance(payload, dict) else []
        logger.info("Superdapp inbound payload keys=%s", payload_keys)

    _check_webhook_secret(request, payload)

    conversation_id = _extract_conversation_id(payload)
    user_message = _extract_message_text(payload)

    if Config.SUPERDAPP_DEBUG_WEBHOOK:
        msg_type = payload.get("type") if isinstance(payload, dict) else None
        preview = (user_message[:120] + "...") if len(user_message) > 120 else user_message
        logger.info(
            "Superdapp parsed conversation_id=%s message_present=%s type=%s preview=%r",
            conversation_id,
            bool(user_message),
            msg_type,
            preview,
        )

    if not user_message:
        # Some providers send non-message webhook events (status, delivery, ping).
        # Acknowledge with 200 to avoid retries and keep integration stable.
        logger.info(
            "Superdapp webhook event without message text. keys=%s",
            sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
        )
        return {
            "ok": True,
            "status": "ok",
            "conversation_id": conversation_id,
            "conversationId": conversation_id,
            "ignored": True,
            "reason": "no_message_text",
            "data": {
                "ignored": True,
                "reason": "no_message_text",
            },
        }

    try:
        response_text = await _process_user_text(conversation_id=conversation_id, message=user_message)
    except CircuitBreakerOpenError as exc:
        response_text = format_llm_circuit_breaker_message(exc)
    except Exception as exc:
        logger.exception("Error processing Superdapp message")
        response_text = f"Error interno procesando mensaje: {str(exc)[:200]}"

    routing_context = payload if isinstance(payload, dict) else {}
    delivered = False
    if Config.SUPERDAPP_ASYNC_DELIVERY_ENABLED:
        delivered = await send_superdapp_message(
            conversation_id=conversation_id,
            message=response_text,
            routing_context=routing_context,
        )
    elif Config.SUPERDAPP_DEBUG_WEBHOOK:
        logger.info("Superdapp async delivery disabled; using sync webhook response only")

    # Superdapp compact sync response format.
    compact_body = quote(json.dumps({"body": response_text}, ensure_ascii=False), safe="")

    chat_id = routing_context.get("chatId") or conversation_id
    room_id = routing_context.get("roomId")
    room_participant_id = routing_context.get("roomParticipantId")
    member_id = routing_context.get("memberId")
    sender_id = routing_context.get("senderId")
    user_id = routing_context.get("userId")

    # Return both compact and plain variants for compatibility across
    # different Superdapp webhook parsers.
    response_payload: dict[str, Any] = {
        "m": compact_body,
        "t": "chat",
        "body": response_text,
        "message": response_text,
        "text": response_text,
        "response": response_text,
    }
    response_payload["data"] = {
        "m": compact_body,
        "t": "chat",
        "body": response_text,
        "message": response_text,
        "text": response_text,
        "response": response_text,
    }
    if chat_id:
        response_payload["chatId"] = chat_id
        response_payload["data"]["chatId"] = chat_id
    if room_id:
        response_payload["roomId"] = room_id
        response_payload["data"]["roomId"] = room_id
    if room_participant_id:
        response_payload["roomParticipantId"] = room_participant_id
        response_payload["data"]["roomParticipantId"] = room_participant_id
    if member_id:
        response_payload["memberId"] = member_id
        response_payload["data"]["memberId"] = member_id
    if sender_id:
        response_payload["senderId"] = sender_id
        response_payload["data"]["senderId"] = sender_id
    if user_id:
        response_payload["userId"] = user_id
        response_payload["data"]["userId"] = user_id

    if Config.SUPERDAPP_ASYNC_DELIVERY_ENABLED:
        if not delivered:
            logger.warning("Superdapp async delivery failed, relying on sync response body")
        elif Config.SUPERDAPP_DEBUG_WEBHOOK:
            logger.info("Superdapp async delivery succeeded for conversation_id=%s", conversation_id)

    if Config.SUPERDAPP_DEBUG_WEBHOOK:
        logger.info("Superdapp sync response payload keys=%s", sorted(response_payload.keys()))

    return response_payload


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
