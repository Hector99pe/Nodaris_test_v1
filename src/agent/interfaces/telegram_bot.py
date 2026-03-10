"""Telegram interface for Nodaris academic audit agent."""

from __future__ import annotations

import html
import logging
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

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

from agent.config import Config
from agent.graph import graph
from agent.state import AcademicAuditState

AUDIT_USAGE: Final[str] = "Uso: /auditar <dni> <nota>. Ejemplo: /auditar 12345678 15"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    _ = context
    if update.message is None:
        return
    await update.message.reply_text(
        "🎓 <b>Nodaris Agent</b> - Auditoría Académica\n\n"
        "Comandos disponibles:\n"
        "• /auditar &lt;dni&gt; &lt;nota&gt; - Auditar registro académico\n"
        "• /help - Ver ayuda\n\n"
        "Escala de notas: 0-20",
        parse_mode=ParseMode.HTML
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    _ = context
    if update.message is None:
        return
    await update.message.reply_text(AUDIT_USAGE)


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

    # Show typing indicator while processing
    await update.message.chat.send_action("typing")

    # Create state object
    state = AcademicAuditState(dni=dni, nota=nota)
    result = await graph.ainvoke(state)

    if result.get("status") == "error":
        error_msg = html.escape(result.get('mensaje', 'sin detalle'))
        await update.message.reply_text(
            f"❌ <b>Error de validación</b>\n{error_msg}",
            parse_mode=ParseMode.HTML
        )
        return

    # Build response with anomaly alert
    anomaly_icon = "⚠️" if result.get("anomalia_detectada") else "✅"
    anomaly_text = "\n\n⚠️ <b>ALERTA: Anomalía detectada</b>" if result.get("anomalia_detectada") else ""

    # Escape HTML in all user-generated content to prevent parsing errors
    dni_value = html.escape(str(result.get('dni', '')))
    nota_value = html.escape(str(result.get('nota', '')))
    hash_value = html.escape(str(result.get('hash', ''))[:16])
    analisis_content = html.escape(result.get('analisis', 'Sin análisis disponible'))

    response = (
        f"{anomaly_icon} <b>Auditoría Completada</b>{anomaly_text}\n\n"
        f"👤 <b>DNI:</b> <code>{dni_value}</code>\n"
        f"📊 <b>Nota:</b> {nota_value}/20\n"
        f"🔐 <b>Hash:</b> <code>{hash_value}...</code>\n\n"
        f"📝 <b>Análisis:</b>\n{analisis_content}"
    )
    await update.message.reply_text(response, parse_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram bot."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Handle specific error types
    if isinstance(context.error, Exception):
        error_name = type(context.error).__name__

        # Send user-friendly message for common errors
        if isinstance(update, Update) and update.effective_message:
            try:
                if "Conflict" in error_name:
                    await update.effective_message.reply_text(
                        "⚠️ Error: Hay otra instancia del bot ejecutándose. "
                        "Por favor, contacta al administrador."
                    )
                else:
                    await update.effective_message.reply_text(
                        "❌ Ocurrió un error inesperado. Por favor, intenta de nuevo."
                    )
            except Exception:
                # If we can't send a message, just log it
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

    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("auditar", auditar_command))

    # Add error handler
    app.add_error_handler(error_handler)

    print("Bot activo y escuchando comandos.")
    print("Presiona Ctrl+C para detener.\n")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
