#!/bin/bash
set -e

echo "🚀 Iniciando Nodaris en Railway..."

# Crear directorios si no existen
mkdir -p data/inbox data/processed data/review data/failed

# Validar configuración
echo "✓ Validando salud del sistema..."
python -m agent.interfaces.health_check || echo "⚠️ Health check completado con advertencias"

# Función para manejar señales
cleanup() {
    echo "⛔ Deteniendo servicios..."
    kill $SCHEDULER_PID $CONSUMER_PID $TELEGRAM_PID 2>/dev/null || true
    wait
    echo "✓ Servicios detenidos"
}

trap cleanup EXIT INT TERM

# Iniciar Scheduler (descubre archivos y encola jobs)
echo "📋 Iniciando Scheduler..."
python -m agent.scheduler.task_scheduler &
SCHEDULER_PID=$!
sleep 2

# Iniciar Queue Consumer (procesa auditorías)
echo "⚙️ Iniciando Queue Consumer..."
python -m agent.interfaces.queue_consumer &
CONSUMER_PID=$!
sleep 2

# Iniciar Telegram Bot (interfaz conversacional)
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "🤖 Iniciando Telegram Bot..."
    python -m agent.interfaces.telegram_bot &
    TELEGRAM_PID=$!
    sleep 2
else
    echo "⚠️ TELEGRAM_BOT_TOKEN no configurado - Telegram Bot deshabilitado"
    TELEGRAM_PID=""
fi

echo "✅ Todos los servicios iniciados"
echo "📊 Monitoreo activo:"
echo "   - Scheduler: descubriendo archivos en data/inbox/"
echo "   - Consumer: procesando auditorías"
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "   - Telegram Bot: escuchando comandos"
fi

# Mantener el contenedor vivo
wait
