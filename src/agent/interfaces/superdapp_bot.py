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
import tempfile
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
from agent.resilience import (
    CircuitBreakerOpenError,
    format_llm_circuit_breaker_message,
    get_llm_circuit_breaker_snapshot,
)
from agent.storage.audit_store import AuditStore

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Nodaris Superdapp Interface", version="1.0.0")
_graph = get_graph_with_memory()

_AUDIT_USAGE = "Uso: /auditar <dni> <nota>. Ejemplo: /auditar 12345678 15"
_REPORT_USAGE = (
    "Uso:\n"
    "- /reporte <audit_id>\n"
    "- /reporte hash <prefijo_hash>\n"
    "- /reporte dni <dni>\n"
    "- /reporte examen <exam_id>\n"
    "- /reporte alumno <dni_o_nombre>"
)
_COMMANDS_MENU = (
    "Comandos disponibles:\n"
    "/start\n"
    "/help\n"
    "/auditar <dni> <nota>\n"
    "/info\n"
    "/auditorias\n"
    "/reporte ...\n"
    "/revision\n"
    "/stats\n"
    "/estado"
)


def _infer_extension_from_payload(payload: dict[str, Any]) -> str:
    """Infer file extension from payload metadata."""
    file_mime = str(payload.get("fileMime") or "").lower().strip()
    file_key = str(payload.get("fileKey") or "").strip()

    if file_mime in {"application/json", "text/json"}:
        return ".json"
    if file_mime in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        return ".csv"

    lower_key = file_key.lower()
    if lower_key.endswith(".json"):
        return ".json"
    if lower_key.endswith(".csv"):
        return ".csv"

    return ""


async def _download_superdapp_file(payload: dict[str, Any]) -> Path:
    """Download attached file from Superdapp event payload into temp path."""
    file_key = str(payload.get("fileKey") or "").strip()
    if not file_key:
        raise RuntimeError("Evento sin fileKey")

    ext = _infer_extension_from_payload(payload)
    if ext not in {".json", ".csv"}:
        raise RuntimeError(
            f"Formato no soportado para adjunto: fileMime={payload.get('fileMime')} fileKey={file_key}"
        )

    api_url = Config.SUPERDAPP_API_URL.strip().rstrip("/")
    api_key = Config.SUPERDAPP_API_KEY
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    candidates: list[str] = []
    if file_key.startswith("http://") or file_key.startswith("https://"):
        candidates.append(file_key)
    else:
        # Best-effort candidate URLs used by common API shapes.
        candidates.extend(
            [
                f"{api_url}/{file_key.lstrip('/')}",
                f"{api_url}/v1/files/{file_key}",
                f"{api_url}/v1/files/{file_key}/download",
                f"{api_url}/v1/agent-bots/files/{file_key}",
                f"{api_url}/v1/agent-bots/files/{file_key}/download",
            ]
        )

    last_error = ""
    data: bytes | None = None
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url in candidates:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code >= 400:
                    last_error = f"{url} -> {resp.status_code}"
                    continue
                data = resp.content
                if data:
                    if Config.SUPERDAPP_DEBUG_WEBHOOK:
                        logger.info("Superdapp file downloaded from %s (%d bytes)", url, len(data))
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = f"{url} -> {exc}"

    if not data:
        raise RuntimeError(f"No se pudo descargar adjunto desde Superdapp. Ultimo error: {last_error}")

    temp_dir = project_root / "temp_uploads"
    temp_dir.mkdir(exist_ok=True)
    local_path = temp_dir / f"superdapp_{uuid.uuid4().hex}{ext}"
    local_path.write_bytes(data)
    return local_path


async def _process_superdapp_file_event(payload: dict[str, Any], thread_id: str) -> str:
    """Process CSV/JSON attachment from Superdapp with the graph file flow."""
    local_path: Path | None = None
    try:
        local_path = await _download_superdapp_file(payload)

        state = {
            "file_path": str(local_path),
            "file_type": local_path.suffix.lstrip("."),
        }
        config = {"configurable": {"thread_id": thread_id}}
        result = await _graph.ainvoke(state, config=config)

        if result.get("status") == "error":
            return f"Error al procesar archivo: {result.get('mensaje', 'sin detalle')}"
        if result.get("reporte_final"):
            return str(result["reporte_final"])
        if result.get("mensaje"):
            return str(result["mensaje"])
        return "Archivo procesado correctamente."
    except Exception as exc:  # noqa: BLE001
        logger.error("Error processing Superdapp file event: %s", exc, exc_info=True)
        return f"No se pudo procesar el archivo adjunto: {str(exc)[:200]}"
    finally:
        if local_path is not None:
            try:
                local_path.unlink(missing_ok=True)
            except Exception:
                pass


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


async def _process_user_text(conversation_id: str, message: str, payload: dict[str, Any] | None = None) -> str:
    """Route Superdapp user message to Nodaris graph."""
    thread_id = f"superdapp_{conversation_id}"
    user_text = (message or "").strip()

    # File parity with Telegram: if an uploaded CSV/JSON is attached, process it.
    if payload and payload.get("fileKey") and bool(payload.get("isUploaded", True)):
        ext = _infer_extension_from_payload(payload)
        if ext in {".csv", ".json"}:
            return await _process_superdapp_file_event(payload, thread_id)

    if not user_text.startswith("/"):
        return await process_conversation(message=user_text, thread_id=thread_id)

    parts = user_text.split()
    command = parts[0].lower()
    args = parts[1:]

    if command == "/start":
        return (
            "Nodaris Agent - Asistente de Auditoria Academica\n\n"
            "Puedes auditar registros, revisar reportes y consultar el estado del sistema.\n\n"
            f"{_COMMANDS_MENU}"
        )

    if command == "/help":
        return (
            "Ayuda de Nodaris\n\n"
            f"{_COMMANDS_MENU}\n\n"
            f"Auditoria rapida:\n{_AUDIT_USAGE}\n\n"
            "Tambien puedes escribir en lenguaje natural para consultas conversacionales."
        )

    if command == "/info":
        cb = get_llm_circuit_breaker_snapshot()
        return (
            "Informacion del Sistema\n\n"
            f"Modelo LLM: {Config.OPENAI_MODEL}\n"
            f"Temperatura: {Config.OPENAI_TEMPERATURE}\n"
            f"Max iteraciones agente: {Config.MAX_AGENT_ITERATIONS}\n"
            f"Max re-planificaciones: {Config.MAX_REFLECTION_REPLANS}\n"
            f"Rango notas validas: {Config.NOTA_MIN}-{Config.NOTA_MAX}\n"
            f"Umbral anomalia: {Config.ANOMALY_THRESHOLD}\n\n"
            f"Circuit Breaker LLM: {cb['state']}\n"
            f"Fallos consecutivos: {cb['consecutive_failures']}\n"
            f"DB: {Config.AUDIT_DB_PATH}\n"
            f"Autonomia: {'Habilitada' if Config.AUTONOMY_ENABLED else 'Deshabilitada'}"
        )

    if command == "/auditorias":
        try:
            audits = AuditStore().list_recent_audits(10)
        except Exception as exc:
            logger.error("Error listing audits: %s", exc)
            return "Error al consultar auditorias."
        if not audits:
            return "No hay auditorias registradas aun."

        lines = ["Ultimas auditorias"]
        for item in audits:
            score = item.get("confidence_score")
            score_text = f"{float(score):.0%}" if score is not None else "N/A"
            lines.append(
                f"#{item['id']} | examen={item.get('exam_id') or '-'} | "
                f"dni={item.get('dni') or '-'} | conf={score_text}"
            )
        return "\n".join(lines)

    if command == "/revision":
        try:
            jobs = AuditStore().list_review_jobs(limit=10)
        except Exception as exc:
            logger.error("Error listing review jobs: %s", exc)
            return "Error al consultar jobs en revision."
        if not jobs:
            return "No hay jobs pendientes de revision manual."

        lines = ["Jobs en revision manual"]
        for job in jobs:
            file_name = Path(str(job.get("source_ref", ""))).name or "-"
            lines.append(
                f"Job #{job['id']} | riesgo={job.get('risk_label')} | "
                f"intentos={job.get('attempt_count')}/{job.get('max_attempts')} | archivo={file_name}"
            )
        return "\n".join(lines)

    if command == "/stats":
        try:
            store = AuditStore()
            stats = store.get_job_stats()
            dead_count = store.get_dead_letter_count()
        except Exception as exc:
            logger.error("Error getting stats: %s", exc)
            return "Error al consultar estadisticas."

        return (
            "Estadisticas de la Cola\n\n"
            f"Pendientes: {stats['pending']}\n"
            f"En proceso: {stats['running']}\n"
            f"Completados: {stats['completed']}\n"
            f"Fallidos: {stats['failed']}\n"
            f"En revision: {stats['review_required']}\n"
            f"Aprobados: {stats['approved']}\n"
            f"Rechazados: {stats['rejected']}\n"
            f"Total: {stats['total']}\n"
            f"Dead-letters: {dead_count}"
        )

    if command == "/estado":
        cb = get_llm_circuit_breaker_snapshot()
        try:
            store = AuditStore()
            stats = store.get_job_stats()
            dead_count = store.get_dead_letter_count()
            queue_line = (
                f"Cola: {stats['pending']} pendientes, {stats['running']} en proceso, "
                f"{stats['completed']} completados"
            )
            dead_line = f"Dead-letters: {dead_count}"
        except Exception:
            queue_line = "Cola: no disponible"
            dead_line = "Dead-letters: no disponible"

        return (
            "Estado del Sistema\n\n"
            f"LLM: {cb['state']}\n"
            f"{queue_line}\n"
            f"{dead_line}\n"
            f"Modelo: {Config.OPENAI_MODEL}\n"
            f"Autonomia: {'Habilitada' if Config.AUTONOMY_ENABLED else 'Deshabilitada'}"
        )

    if command == "/reporte":
        if not args:
            return _REPORT_USAGE

        store = AuditStore()
        report: dict[str, Any] | None = None

        try:
            if len(args) == 1 and args[0].isdigit():
                report = store.get_audit_report_by_id(int(args[0]))
            elif len(args) >= 2:
                key = args[0].lower().strip()
                value = " ".join(args[1:]).strip()
                if not value:
                    return _REPORT_USAGE

                if key == "hash":
                    matches = store.find_audits(hash_prefix=value, limit=10)
                elif key == "dni":
                    matches = store.find_audits(dni=value, limit=10)
                elif key in {"examen", "exam"}:
                    matches = store.find_audits(exam_id=value, limit=10)
                elif key == "alumno":
                    matches = store.find_audits(alumno=value, limit=10)
                else:
                    return f"Filtro no soportado: {key}\n\n{_REPORT_USAGE}"

                if not matches:
                    return "No se encontraron reportes para ese criterio."
                report = matches[0]
            else:
                return _REPORT_USAGE
        except Exception as exc:
            logger.error("Error getting report: %s", exc, exc_info=True)
            return "Error al consultar el reporte solicitado."

        if not report:
            return "No se encontro el reporte solicitado."

        report_text = str(report.get("report_text") or "")
        if not report_text.strip():
            return "El reporte existe pero no tiene contenido de texto."

        meta = (
            f"Reporte #{report['id']}\n"
            f"Examen: {report.get('exam_id') or '-'}\n"
            f"DNI: {report.get('dni') or '-'}\n"
            f"Hash: {(report.get('audit_hash') or '')[:16]}"
        )
        return f"{meta}\n\n{report_text}"

    if command == "/auditar":
        if len(args) != 2:
            return _AUDIT_USAGE

        dni = args[0]
        try:
            nota = int(args[1])
        except ValueError:
            return f"La nota debe ser numerica.\n\n{_AUDIT_USAGE}"

        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = await _graph.ainvoke({"dni": dni, "nota": nota}, config=config)
        except CircuitBreakerOpenError as exc:
            return format_llm_circuit_breaker_message(exc)

        if result.get("status") == "error":
            return f"Error de validacion: {result.get('mensaje', 'sin detalle')}"
        if result.get("reporte_final"):
            return str(result["reporte_final"])
        if result.get("mensaje"):
            return str(result["mensaje"])
        return "Auditoria completada."

    return await process_conversation(message=user_text, thread_id=thread_id)


async def send_superdapp_message(
    conversation_id: str,
    message: str,
    routing_context: dict[str, Any] | None = None,
) -> bool:
    """Send assistant response back to Superdapp through REST API."""

    def _compute_room_id(ctx: dict[str, Any], fallback: str) -> str:
        # Prefer explicit IDs provided by Superdapp event payload.
        explicit_room = str(ctx.get("roomId") or "").strip()
        if explicit_room:
            return explicit_room

        chat_id = str(ctx.get("chatId") or "").strip()
        if chat_id:
            return chat_id

        member_id = str(ctx.get("memberId") or "").strip()
        sender_id = str(ctx.get("senderId") or "").strip()
        owner_id = str(ctx.get("owner") or "").strip()

        if member_id and sender_id and member_id != sender_id:
            return f"{member_id}-{sender_id}"
        if owner_id and sender_id:
            return f"{owner_id}-{sender_id}"

        return fallback

    def _room_id_candidates(ctx: dict[str, Any], fallback: str) -> list[str]:
        """Build ordered roomId candidates to handle tenant-specific ID conventions."""
        candidates: list[str] = []

        def _add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in candidates:
                candidates.append(text)

        explicit_room = str(ctx.get("roomId") or "").strip()
        chat_id = str(ctx.get("chatId") or "").strip()
        member_id = str(ctx.get("memberId") or "").strip()
        sender_id = str(ctx.get("senderId") or "").strip()
        owner_id = str(ctx.get("owner") or "").strip()

        # Prefer IDs emitted by incoming event.
        _add(explicit_room)
        _add(chat_id)

        # SDK-style composition and reverse variant.
        if member_id and sender_id:
            _add(f"{member_id}-{sender_id}")
            _add(f"{sender_id}-{member_id}")
        if owner_id and sender_id:
            _add(f"{owner_id}-{sender_id}")
            _add(f"{sender_id}-{owner_id}")

        _add(fallback)
        return candidates

    api_url = Config.SUPERDAPP_API_URL.strip()
    api_key = Config.SUPERDAPP_API_KEY
    endpoint_template = Config.SUPERDAPP_SEND_ENDPOINT.strip()
    if not endpoint_template:
        endpoint_template = "v1/agent-bots/connections/{roomId}/messages"

    ctx = routing_context or {}
    room_id = _compute_room_id(ctx, conversation_id)
    candidate_room_ids = _room_id_candidates(ctx, conversation_id)

    if Config.SUPERDAPP_DEBUG_WEBHOOK:
        logger.info(
            "Superdapp routing ids roomId=%r chatId=%r memberId=%r senderId=%r owner=%r chosen_room_id=%r",
            ctx.get("roomId"),
            ctx.get("chatId"),
            ctx.get("memberId"),
            ctx.get("senderId"),
            ctx.get("owner"),
            room_id,
        )

    if not api_url or not api_key:
        logger.warning("Superdapp API not configured (SUPERDAPP_API_URL/SUPERDAPP_API_KEY)")
        return False

    compact_body = quote(json.dumps({"body": message}, ensure_ascii=False), safe="")
    formatted_body = json.dumps({"m": compact_body, "t": "chat"}, ensure_ascii=False)
    payload: dict[str, Any] = {
        "message": {
            "body": formatted_body,
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for candidate in candidate_room_ids:
        endpoint = endpoint_template.replace("{roomId}", candidate)
        url = f"{api_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            if Config.SUPERDAPP_DEBUG_WEBHOOK:
                logger.info("Superdapp async delivery target url=%s room_id=%s", url, candidate)
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if Config.SUPERDAPP_DEBUG_WEBHOOK:
                    preview = response.text[:300].replace("\n", " ")
                    logger.info(
                        "Superdapp async delivery response status=%s body=%r",
                        response.status_code,
                        preview,
                    )

                if response.status_code >= 400:
                    response.raise_for_status()

                # Some APIs return 200 but indicate failure in JSON payload.
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        lowered_keys = {str(k).lower(): v for k, v in data.items()}
                        if lowered_keys.get("ok") is False or lowered_keys.get("success") is False:
                            logger.warning("Superdapp API returned logical failure payload: %s", data)
                            continue
                except Exception:
                    pass
            return True
        except Exception as exc:
            last_error = exc
            if Config.SUPERDAPP_DEBUG_WEBHOOK:
                logger.warning("Superdapp async attempt failed for room_id=%s: %s", candidate, exc)
            continue

    if last_error:
        logger.error("Failed to deliver message to Superdapp API after all roomId candidates: %s", last_error)
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
        response_text = await _process_user_text(
            conversation_id=conversation_id,
            message=user_message,
            payload=payload if isinstance(payload, dict) else None,
        )
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

    sync_t = (Config.SUPERDAPP_SYNC_T or "message").strip() or "message"

    # Strict mode emulates SDK-like compact response (`m` + `t`) to avoid
    # parser ambiguity in some Superdapp tenants.
    if Config.SUPERDAPP_SYNC_STRICT_MODE:
        compact_message = {"m": compact_body, "t": sync_t}
        response_payload: dict[str, Any] = {
            "body": json.dumps(compact_message, ensure_ascii=False),
            "isSilent": False,
        }
    else:
        # Extended mode keeps aliases for broader compatibility.
        compact_message = {"m": compact_body, "t": sync_t}
        response_payload = {
            "m": compact_body,
            "t": sync_t,
            "isSilent": False,
            "body": response_text,
            "message": response_text,
            "text": response_text,
            "response": response_text,
            "data": {
                "body": json.dumps(compact_message, ensure_ascii=False),
                "isSilent": False,
                "m": compact_body,
                "t": sync_t,
                "message": response_text,
                "text": response_text,
                "response": response_text,
            },
        }
    if not Config.SUPERDAPP_SYNC_STRICT_MODE:
        if chat_id:
            response_payload["chatId"] = chat_id
            if isinstance(response_payload.get("data"), dict):
                response_payload["data"]["chatId"] = chat_id
        if room_id:
            response_payload["roomId"] = room_id
            if isinstance(response_payload.get("data"), dict):
                response_payload["data"]["roomId"] = room_id
        if room_participant_id:
            response_payload["roomParticipantId"] = room_participant_id
            if isinstance(response_payload.get("data"), dict):
                response_payload["data"]["roomParticipantId"] = room_participant_id
        if member_id:
            response_payload["memberId"] = member_id
            if isinstance(response_payload.get("data"), dict):
                response_payload["data"]["memberId"] = member_id
        if sender_id:
            response_payload["senderId"] = sender_id
            if isinstance(response_payload.get("data"), dict):
                response_payload["data"]["senderId"] = sender_id
        if user_id:
            response_payload["userId"] = user_id
            if isinstance(response_payload.get("data"), dict):
                response_payload["data"]["userId"] = user_id

    if Config.SUPERDAPP_ASYNC_DELIVERY_ENABLED:
        if not delivered:
            logger.warning("Superdapp async delivery failed, relying on sync response body")
        elif Config.SUPERDAPP_DEBUG_WEBHOOK:
            logger.info("Superdapp async delivery succeeded for conversation_id=%s", conversation_id)

    if Config.SUPERDAPP_DEBUG_WEBHOOK:
        logger.info(
            "Superdapp sync response mode=%s t=%s payload keys=%s",
            "strict" if Config.SUPERDAPP_SYNC_STRICT_MODE else "extended",
            sync_t,
            sorted(response_payload.keys()),
        )

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
