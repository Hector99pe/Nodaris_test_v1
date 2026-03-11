"""Telegram interface for Nodaris academic audit agent."""

from __future__ import annotations

import html
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load .env BEFORE importing Config (which reads env vars at import time)
project_root = Path(__file__).resolve().parent.parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Add src to path for imports if needed
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from agent.config import Config
from agent.graph.graph import get_graph_with_memory, clear_tool_cache
from agent.conversation import process_conversation
from agent.resilience import CircuitBreakerOpenError, format_llm_circuit_breaker_message, get_llm_circuit_breaker_snapshot
from agent.storage.audit_store import AuditStore

# Graph with memory checkpointer for Telegram persistence
_graph = get_graph_with_memory()

AUDIT_USAGE: Final[str] = "Uso: /auditar &lt;dni&gt; &lt;nota&gt;. Ejemplo: /auditar 12345678 15"

# Track pending interrupts per chat (for human-in-the-loop)
pending_interrupts: dict[int, str] = {}  # chat_id -> thread_id

# Cache exam data per chat so file data persists to conversations
_chat_exam_cache: dict[int, dict] = {}  # chat_id -> {exam_data, students_data, file_name}

# Dynamic chat thread ids — reset on each file upload to avoid stale checkpointed data
_chat_thread_ids: dict[int, str] = {}  # chat_id -> thread_id

# Progress messages for streaming feedback
_PROGRESS_MESSAGES = [
    "📋 Planificando auditoría...",
    "🔍 Analizando datos...",
    "🤖 Ejecutando herramientas de análisis...",
    "📊 Evaluando resultados...",
    "📝 Generando reporte...",
]


async def _send_progress(chat, stage: int) -> None:
    """Send a progress indicator to the user."""
    if 0 <= stage < len(_PROGRESS_MESSAGES):
        try:
            await chat.send_action("typing")
            await chat.send_message(_PROGRESS_MESSAGES[stage])
        except Exception:
            pass  # Progress messages are best-effort


_COMMANDS_MENU: Final[str] = (
    "<b>Comandos disponibles:</b>\n"
    "• /help - Menú de ayuda completo\n"
    "• /info - Información del sistema\n"
    "• /auditar &lt;dni&gt; &lt;nota&gt; - Auditoría rápida\n"
    "• /auditorias - Últimas auditorías registradas\n"
    "• /stats - Estadísticas de la cola de jobs\n"
    "• /estado - Estado operativo del sistema"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    _ = context
    if update.message is None:
        return

    chat_id = update.message.chat_id
    pending_interrupts.pop(chat_id, None)

    await update.message.reply_text(
        "🎓 <b>Nodaris Agent</b> - Asistente de Auditoría Académica\n\n"
        "¡Hola! Soy Nodaris, tu asistente inteligente para auditorías académicas.\n\n"
        "<b>Puedes:</b>\n"
        "• Escribirme en lenguaje natural\n"
        "• Pedirme auditar un registro\n"
        "• Enviarme archivos (CSV, JSON) para auditar\n"
        "• Verificar hashes de autenticación\n"
        "• Consultar sobre el sistema de notas\n\n"
        f"{_COMMANDS_MENU}\n\n"
        "<i>Ejemplo: 'Audita el registro del DNI 12345678 con nota 15'</i>",
        parse_mode=ParseMode.HTML
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    _ = context
    if update.message is None:
        return
    await update.message.reply_text(
        "📖 <b>Ayuda de Nodaris</b>\n\n"
        f"{_COMMANDS_MENU}\n\n"
        "<b>Auditoría rápida:</b>\n"
        f"{AUDIT_USAGE}\n\n"
        "<b>Archivos soportados:</b>\n"
        "📄 CSV, JSON\n"
        "Envía un archivo directamente al chat para auditarlo.\n\n"
        "<b>Conversación libre:</b>\n"
        "También puedes escribirme en lenguaje natural.\n"
        "<i>Ejemplo: 'Audita el registro del DNI 12345678 con nota 15'</i>",
        parse_mode=ParseMode.HTML
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /info command - show system information."""
    _ = context
    if update.message is None:
        return

    cb = get_llm_circuit_breaker_snapshot()
    cb_state = cb["state"]
    cb_icon = "🟢" if cb_state == "closed" else ("🟡" if cb_state == "half_open" else "🔴")

    await update.message.reply_text(
        "ℹ️ <b>Información del Sistema</b>\n\n"
        f"🤖 <b>Modelo LLM:</b> {html.escape(Config.OPENAI_MODEL)}\n"
        f"🌡️ <b>Temperatura:</b> {Config.OPENAI_TEMPERATURE}\n"
        f"🔄 <b>Máx. iteraciones agente:</b> {Config.MAX_AGENT_ITERATIONS}\n"
        f"🔁 <b>Máx. re-planificaciones:</b> {Config.MAX_REFLECTION_REPLANS}\n"
        f"📊 <b>Rango notas válidas:</b> {Config.NOTA_MIN}-{Config.NOTA_MAX}\n"
        f"🎯 <b>Umbral anomalía:</b> {Config.ANOMALY_THRESHOLD}\n\n"
        f"{cb_icon} <b>Circuit Breaker LLM:</b> {cb_state}\n"
        f"  Fallos consecutivos: {cb['consecutive_failures']}\n"
        f"  Último error: {html.escape(cb['last_error'][:80]) if cb['last_error'] else 'Ninguno'}\n\n"
        f"🗃️ <b>Base de datos:</b> {html.escape(Config.AUDIT_DB_PATH)}\n"
        f"📂 <b>Autonomía:</b> {'Habilitada' if Config.AUTONOMY_ENABLED else 'Deshabilitada'}\n"
        f"🧠 <b>Memoria de aprendizaje:</b> {'Activa' if Config.LEARNING_MEMORY_ENABLED else 'Inactiva'}",
        parse_mode=ParseMode.HTML
    )


async def auditorias_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /auditorias command - list recent audits."""
    _ = context
    if update.message is None:
        return

    try:
        store = AuditStore()
        audits = store.list_recent_audits(10)
    except Exception as e:
        logger.error("Error listing audits: %s", e)
        await update.message.reply_text("❌ Error al consultar auditorías.")
        return

    if not audits:
        await update.message.reply_text("📋 No hay auditorías registradas aún.")
        return

    lines = ["📋 <b>Últimas auditorías</b>\n"]
    for a in audits:
        score = a["confidence_score"]
        score_str = f"{score:.0%}" if score is not None else "N/A"
        mode = a["input_mode"] or "—"
        status = a["status"] or "—"
        date = str(a["created_at"])[:16].replace("T", " ")
        dni = a["dni"] or "—"
        hash_short = a["audit_hash"][:8] if a["audit_hash"] else "—"

        icon = "✅" if status == "success" else ("❌" if status == "error" else "⏳")
        lines.append(
            f"{icon} <b>#{a['id']}</b> | {html.escape(date)}\n"
            f"   Modo: {html.escape(mode)} | DNI: {html.escape(dni)}\n"
            f"   Confianza: {score_str} | Hash: <code>{html.escape(hash_short)}</code>"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - show job queue statistics."""
    _ = context
    if update.message is None:
        return

    try:
        store = AuditStore()
        stats = store.get_job_stats()
        dead_count = store.get_dead_letter_count()
    except Exception as e:
        logger.error("Error getting stats: %s", e)
        await update.message.reply_text("❌ Error al consultar estadísticas.")
        return

    await update.message.reply_text(
        "📊 <b>Estadísticas de la Cola</b>\n\n"
        f"⏳ Pendientes: <b>{stats['pending']}</b>\n"
        f"▶️ En proceso: <b>{stats['running']}</b>\n"
        f"✅ Completados: <b>{stats['completed']}</b>\n"
        f"❌ Fallidos: <b>{stats['failed']}</b>\n"
        f"🔍 En revisión: <b>{stats['review_required']}</b>\n"
        f"👍 Aprobados: <b>{stats['approved']}</b>\n"
        f"👎 Rechazados: <b>{stats['rejected']}</b>\n\n"
        f"📦 <b>Total jobs:</b> {stats['total']}\n"
        f"💀 <b>Dead-letters:</b> {dead_count}",
        parse_mode=ParseMode.HTML
    )


async def estado_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /estado command - operational health overview."""
    _ = context
    if update.message is None:
        return

    # Circuit breaker status
    cb = get_llm_circuit_breaker_snapshot()
    cb_state = cb["state"]
    if cb_state == "closed":
        cb_line = "🟢 <b>LLM:</b> Operativo"
    elif cb_state == "half_open":
        cb_line = "🟡 <b>LLM:</b> Recuperándose"
    else:
        wait = int(cb["retry_after_sec"])
        cb_line = f"🔴 <b>LLM:</b> Protegido (reintento en {wait}s)"

    # Job queue + dead-letter
    try:
        store = AuditStore()
        stats = store.get_job_stats()
        dead_count = store.get_dead_letter_count()
        queue_line = (
            f"📦 <b>Cola:</b> {stats['pending']} pendientes, "
            f"{stats['running']} en proceso, "
            f"{stats['completed']} completados"
        )
        dead_line = f"💀 <b>Dead-letters:</b> {dead_count}"
        failed_line = f"❌ <b>Fallidos:</b> {stats['failed']}"
        review_line = f"🔍 <b>En revisión:</b> {stats['review_required']}"
    except Exception:
        queue_line = "📦 <b>Cola:</b> No disponible"
        dead_line = "💀 <b>Dead-letters:</b> No disponible"
        failed_line = ""
        review_line = ""

    parts = [
        "🏥 <b>Estado del Sistema</b>\n",
        cb_line,
        queue_line,
        failed_line,
        review_line,
        dead_line,
        f"\n🤖 Modelo: {html.escape(Config.OPENAI_MODEL)}",
        f"📂 Autonomía: {'Habilitada' if Config.AUTONOMY_ENABLED else 'Deshabilitada'}",
    ]
    await update.message.reply_text(
        "\n".join(p for p in parts if p),
        parse_mode=ParseMode.HTML
    )


async def auditar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Audit a student grade from telegram command args."""
    if update.message is None:
        return

    if not context.args or len(context.args) != 2:
        await update.message.reply_text(f"❌ {AUDIT_USAGE}", parse_mode=ParseMode.HTML)
        return

    dni = context.args[0]
    try:
        nota = int(context.args[1])
    except ValueError:
        await update.message.reply_text(f"❌ La nota debe ser numérica.\n\n{AUDIT_USAGE}", parse_mode=ParseMode.HTML)
        return

    await update.message.chat.send_action("typing")
    await update.message.reply_text("📋 Iniciando auditoría individual...")

    chat_id = update.message.chat_id
    thread_id = f"audit_{chat_id}_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    state = {"dni": dni, "nota": nota}
    try:
        result = await _graph.ainvoke(state, config=config)
    except CircuitBreakerOpenError as exc:
        await update.message.reply_text(format_llm_circuit_breaker_message(exc))
        return

    if result.get("status") == "error":
        error_msg = html.escape(result.get('mensaje', 'sin detalle'))
        await update.message.reply_text(
            f"❌ <b>Error de validación</b>\n{error_msg}",
            parse_mode=ParseMode.HTML
        )
        return

    # Send report if available
    if result.get("reporte_final"):
        await update.message.reply_text(result["reporte_final"])
        return

    # Fallback: build response from state fields
    anomaly_icon = "⚠️" if result.get("anomalia_detectada") else "✅"
    anomaly_text = "\n\n⚠️ <b>ALERTA: Anomalía detectada</b>" if result.get("anomalia_detectada") else ""

    dni_value = html.escape(str(result.get('dni', '')))
    nota_value = html.escape(str(result.get('nota', '')))
    hash_value = html.escape(str(result.get('hash', ''))[:16])

    response = (
        f"{anomaly_icon} <b>Auditoría Completada</b>{anomaly_text}\n\n"
        f"👤 <b>DNI:</b> <code>{dni_value}</code>\n"
        f"📊 <b>Nota:</b> {nota_value}/20\n"
        f"🔐 <b>Hash:</b> <code>{hash_value}...</code>"
    )
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document uploads (CSV, JSON) for audit."""
    _ = context
    if update.message is None or update.message.document is None:
        return

    document = update.message.document
    file_name = document.file_name or "unknown"
    file_ext = Path(file_name).suffix.lower()

    supported = {".json", ".csv"}
    if file_ext not in supported:
        await update.message.reply_text(
            f"❌ Formato no soportado: {html.escape(file_ext)}\n"
            f"Formatos aceptados: {', '.join(sorted(supported))}",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.chat.send_action("typing")
    await update.message.reply_text(f"📁 Archivo recibido: {html.escape(file_name)}\n🔄 Procesando...")

    # Download file to temp directory
    file = await document.get_file()
    temp_dir = project_root / "temp_uploads"
    temp_dir.mkdir(exist_ok=True)
    local_path = temp_dir / f"{uuid.uuid4().hex}_{file_name}"
    await file.download_to_drive(str(local_path))

    chat_id = update.message.chat_id
    thread_id = f"file_{chat_id}_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # Clear stale cache and tool-result cache from previous uploads
    _chat_exam_cache.pop(chat_id, None)
    clear_tool_cache()

    # Reset the chat thread so follow-up messages don't see old checkpointed data
    _chat_thread_ids[chat_id] = f"chat_{chat_id}_{uuid.uuid4().hex[:8]}"

    caption = update.message.caption or f"Audita los datos del archivo {file_name}"

    state = {
        "file_path": str(local_path),
        "file_type": file_ext.lstrip("."),
        "messages": [HumanMessage(content=caption)],
    }

    try:
        result = await _graph.ainvoke(state, config=config)

        # Check for pending interrupts (human-in-the-loop)
        graph_state = await _graph.aget_state(config)
        if graph_state.next:
            # Graph was interrupted - send clarification to user
            for task in graph_state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupt_data = task.interrupts[0].value
                    question = interrupt_data.get("pregunta", "¿Necesitas aclaración?")
                    opciones = interrupt_data.get("opciones", "")
                    msg = f"❓ <b>Necesito tu ayuda:</b>\n\n{html.escape(str(question))}"
                    if opciones:
                        msg += f"\n\n<i>Opciones: {html.escape(str(opciones))}</i>"
                    pending_interrupts[chat_id] = thread_id
                    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
                    return

        # Check for error status (data couldn't be read/parsed)
        if result.get("status") == "error":
            error_msg = html.escape(result.get("mensaje", "No se pudieron leer los datos del archivo."))
            await update.message.reply_text(
                f"❌ <b>Error</b>\n{error_msg}",
                parse_mode=ParseMode.HTML,
            )
            return

        # Cache exam data so subsequent conversations can access it
        cached: dict = {}
        if result.get("exam_data"):
            cached["exam_data"] = result["exam_data"]
        if result.get("students_data"):
            cached["students_data"] = result["students_data"]
        if cached:
            cached["file_name"] = file_name
            _chat_exam_cache[chat_id] = cached
            logger.info("Cached exam data for chat %s (%d students)", chat_id,
                        len(cached.get("students_data", [])))

        # Send report
        if result.get("reporte_final"):
            await update.message.reply_text(result["reporte_final"])
        else:
            await update.message.reply_text(
                result.get("mensaje", "Archivo procesado. No se generó reporte.")
            )
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        if isinstance(e, CircuitBreakerOpenError):
            await update.message.reply_text(format_llm_circuit_breaker_message(e))
        else:
            short_err = html.escape(str(e)[:200])
            await update.message.reply_text(
                f"❌ <b>Error al procesar el archivo</b>\n<code>{short_err}</code>",
                parse_mode=ParseMode.HTML,
            )
    finally:
        # Clean up temp file
        try:
            local_path.unlink(missing_ok=True)
        except OSError:
            pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle conversational messages using AI."""
    _ = context
    if update.message is None or update.message.text is None:
        return

    chat_id = update.message.chat_id
    user_message = update.message.text

    await update.message.chat.send_action("typing")

    try:
        # Check for pending interrupt (user responding to clarification)
        if chat_id in pending_interrupts:
            thread_id = pending_interrupts.pop(chat_id)
            config = {"configurable": {"thread_id": thread_id}}
            result = await _graph.ainvoke(
                Command(resume=user_message), config=config
            )

            # Check for more interrupts
            graph_state = await _graph.aget_state(config)
            if graph_state.next:
                for task in graph_state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_data = task.interrupts[0].value
                        question = interrupt_data.get("pregunta", "¿Necesitas aclaración?")
                        pending_interrupts[chat_id] = thread_id
                        await update.message.reply_text(
                            f"❓ {html.escape(str(question))}"
                        )
                        return

            if result.get("reporte_final"):
                await update.message.reply_text(result["reporte_final"])
            else:
                messages = result.get("messages", [])
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        await update.message.reply_text(msg.content)
                        return
                await update.message.reply_text(
                    result.get("mensaje", "Procesado correctamente.")
                )
            return

        # Normal conversation — inject cached exam data as state if available
        # Use dynamic thread_id that resets on each file upload
        if chat_id not in _chat_thread_ids:
            _chat_thread_ids[chat_id] = f"chat_{chat_id}_{uuid.uuid4().hex[:8]}"
        thread_id = _chat_thread_ids[chat_id]

        extra_state: dict = {}
        if chat_id in _chat_exam_cache:
            cache = _chat_exam_cache[chat_id]
            if cache.get("exam_data"):
                extra_state["exam_data"] = cache["exam_data"]
            if cache.get("students_data"):
                extra_state["students_data"] = cache["students_data"]
        else:
            # No cached data — explicitly clear any stale checkpointed values
            extra_state["exam_data"] = {}
            extra_state["students_data"] = []

        response = await process_conversation(
            user_message, thread_id=thread_id, extra_state=extra_state
        )
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)

        error_message = "❌ Ocurrió un error al procesar tu mensaje."

        if isinstance(e, CircuitBreakerOpenError):
            error_message = format_llm_circuit_breaker_message(e)
        elif "insufficient_quota" in str(e):
            error_message = (
                "⚠️ <b>Error de cuota OpenAI</b>\n\n"
                "La cuenta de OpenAI ha excedido su cuota disponible.\n\n"
                "📝 <b>Solución:</b>\n"
                "• Visita: https://platform.openai.com/account/billing\n"
                "• Agrega créditos a tu cuenta\n"
                "• Verifica tu plan y límites"
            )
        elif "model_not_found" in str(e) or "does not exist" in str(e):
            error_message = (
                "⚠️ <b>Modelo no disponible</b>\n\n"
                "El modelo de IA configurado no está disponible en tu cuenta."
            )
        elif "rate_limit" in str(e).lower():
            error_message = (
                "⚠️ <b>Límite de solicitudes alcanzado</b>\n\n"
                "Por favor, espera un momento e intenta de nuevo."
            )
        else:
            error_message += "\n\nPor favor, intenta de nuevo."

        await update.message.reply_text(error_message, parse_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram bot."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            if isinstance(context.error, Exception) and "Conflict" in type(context.error).__name__:
                await update.effective_message.reply_text(
                    "⚠️ Hay otra instancia del bot ejecutándose."
                )
            else:
                await update.effective_message.reply_text(
                    "❌ Ocurrió un error inesperado. Por favor, intenta de nuevo."
                )
        except Exception:
            pass


def run_telegram_bot() -> None:
    """Start telegram bot polling loop."""
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        msg = (
            f"Falta TELEGRAM_BOT_TOKEN en variables de entorno (.env).\n"
            f"Ruta buscada: {env_path}\n"
            f"Archivo existe: {env_path.exists()}\n"
            "Crea un archivo .env con: TELEGRAM_BOT_TOKEN=tu_token_aqui"
        )
        raise ValueError(msg)

    print("Iniciando Nodaris Telegram Bot...")
    print("Conectando...")

    app = Application.builder().token(token).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("auditar", auditar_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("auditorias", auditorias_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("estado", estado_command))

    # Document handler (CSV, JSON)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Conversational message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    print("Bot activo y escuchando comandos.")
    print("Presiona Ctrl+C para detener.\n")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
