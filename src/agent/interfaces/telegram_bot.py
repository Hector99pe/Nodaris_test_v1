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
from agent.graph.graph import get_graph_with_memory
from agent.conversation import process_conversation
from agent.resilience import CircuitBreakerOpenError, format_llm_circuit_breaker_message

# Graph with memory checkpointer for Telegram persistence
_graph = get_graph_with_memory()

AUDIT_USAGE: Final[str] = "Uso: /auditar <dni> <nota>. Ejemplo: /auditar 12345678 15"

# Track pending interrupts per chat (for human-in-the-loop)
pending_interrupts: dict[int, str] = {}  # chat_id -> thread_id


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
        "• Enviarme archivos (Excel, PDF, JSON) para auditar\n"
        "• Verificar hashes de autenticación\n"
        "• Consultar sobre el sistema de notas\n\n"
        "<b>Comandos:</b>\n"
        "• /auditar &lt;dni&gt; &lt;nota&gt; - Auditoría rápida\n"
        "• /help - Ver ayuda\n\n"
        "<i>Ejemplo: 'Audita el registro del DNI 12345678 con nota 15'</i>",
        parse_mode=ParseMode.HTML
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    _ = context
    if update.message is None:
        return
    await update.message.reply_text(
        f"{AUDIT_USAGE}\n\n"
        "También puedes enviarme archivos Excel, PDF o JSON con datos de exámenes."
    )


async def auditar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Audit a student grade from telegram command args."""
    if update.message is None:
        return

    if not context.args or len(context.args) != 2:
        await update.message.reply_text(f"❌ {AUDIT_USAGE}")
        return

    dni = context.args[0]
    try:
        nota = int(context.args[1])
    except ValueError:
        await update.message.reply_text(f"❌ La nota debe ser numérica.\n\n{AUDIT_USAGE}")
        return

    await update.message.chat.send_action("typing")

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
    """Handle document uploads (Excel, PDF, JSON) for audit."""
    _ = context
    if update.message is None or update.message.document is None:
        return

    document = update.message.document
    file_name = document.file_name or "unknown"
    file_ext = Path(file_name).suffix.lower()

    supported = {".json", ".xlsx", ".xls", ".pdf", ".csv"}
    if file_ext not in supported:
        await update.message.reply_text(
            f"❌ Formato no soportado: {html.escape(file_ext)}\n"
            f"Formatos aceptados: {', '.join(sorted(supported))}",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.chat.send_action("typing")

    # Download file to temp directory
    file = await document.get_file()
    temp_dir = project_root / "temp_uploads"
    temp_dir.mkdir(exist_ok=True)
    local_path = temp_dir / f"{uuid.uuid4().hex}_{file_name}"
    await file.download_to_drive(str(local_path))

    chat_id = update.message.chat_id
    thread_id = f"file_{chat_id}_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

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
            await update.message.reply_text("❌ Error al procesar el archivo. Intenta de nuevo.")
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

        # Normal conversation
        thread_id = f"chat_{chat_id}"
        response = await process_conversation(
            user_message, thread_id=thread_id
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

    # Document handler (Excel, PDF, JSON)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Conversational message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    print("Bot activo y escuchando comandos.")
    print("Presiona Ctrl+C para detener.\n")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
