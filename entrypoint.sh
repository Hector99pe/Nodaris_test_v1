#!/bin/bash
set -o pipefail

echo "🚀 Iniciando Nodaris en Railway..."

# Crear directorios si no existen
mkdir -p data/inbox data/processed data/review data/failed

# Validar configuración
echo "✓ Validando salud del sistema..."
python -m agent.interfaces.health_check 2>&1 || echo "⚠️ Health check completado con advertencias"

# Arrays para almacenar PIDs
declare -a PIDS

# Función para manejar señales
cleanup() {
    echo "⛔ Deteniendo servicios..."
    for pid in "${PIDS[@]}"; do
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "✓ Servicios detenidos"
}

trap cleanup EXIT INT TERM

# Función para lanzar un proceso en background con reintentos
launch_service() {
    local name=$1
    local command=$2
    local max_retries=3
    local retry_delay=5

    for attempt in $(seq 1 $max_retries); do
        echo "🔄 $name - Intento $attempt/$max_retries..."
        eval "$command" &
        local pid=$!
        PIDS+=($pid)

        # Esperar 5 segundos para ver si el proceso falla inmediatamente
        sleep 5
        if ! ps -p $pid > /dev/null 2>&1; then
            echo "⚠️ $name falló en intento $attempt"
            if [ $attempt -lt $max_retries ]; then
                echo "🔄 Reintentando en $retry_delay segundos..."
                sleep $retry_delay
            fi
        else
            echo "✅ $name iniciado correctamente (PID: $pid)"
            return 0
        fi
    done

    echo "❌ $name no pudo iniciarse después de $max_retries intentos"
    return 1
}

# Iniciar Scheduler (descubre archivos y encola jobs)
echo "📋 Iniciando Scheduler..."
launch_service "Scheduler" "python -m agent.scheduler.task_scheduler"

# Iniciar Queue Consumer (procesa auditorías)
echo "⚙️ Iniciando Queue Consumer..."
launch_service "Queue Consumer" "python -m agent.interfaces.queue_consumer"

# Iniciar Telegram Bot (interfaz conversacional)
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "🤖 Iniciando Telegram Bot..."
    launch_service "Telegram Bot" "python -m agent.interfaces.telegram_bot"
else
    echo "⚠️ TELEGRAM_BOT_TOKEN no configurado - Telegram Bot deshabilitado"
fi

# Iniciar Superdapp Webhook (API FastAPI)
if [ -n "$SUPERDAPP_API_KEY" ]; then
    echo "🌐 Iniciando Superdapp Webhook..."
    launch_service "Superdapp Webhook" "python -m agent.interfaces.superdapp_bot"
else
    echo "⚠️ SUPERDAPP_API_KEY no configurado - Superdapp Webhook deshabilitado"
fi

echo "✅ Todos los servicios iniciados"
echo "📊 Monitoreo activo:"
echo "   - Scheduler: descubriendo archivos en data/inbox/"
echo "   - Consumer: procesando auditorías"
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "   - Telegram Bot: escuchando comandos"
fi
if [ -n "$SUPERDAPP_API_KEY" ]; then
    port=${PORT:-8080}
    echo "   - Superdapp Webhook: http://0.0.0.0:$port/superdapp/webhook"
fi

# Mantener el contenedor vivo monitoreando procesos
echo "🔍 Monitoreando procesos..."
while true; do
    sleep 10
    for pid in "${PIDS[@]}"; do
        if ! ps -p $pid > /dev/null 2>&1; then
            echo "⚠️ Proceso $pid terminó inesperadamente. Deteniendo contenedor..."
            exit 1
        fi
    done
done
