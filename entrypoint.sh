#!/bin/bash
set -o pipefail

echo "Iniciando Nodaris en Railway..."

# Crear directorios de trabajo
mkdir -p data/inbox data/processed data/review data/failed

# Validacion best-effort
echo "Validando salud del sistema..."
python -m agent.interfaces.health_check 2>&1 || echo "Health check con advertencias"

# Inicia servicios auxiliares sin volverlos criticos para el webhook.
start_optional_service() {
    local name="$1"
    local command="$2"
    echo "Iniciando $name..."
    bash -lc "$command" &
    echo "$name PID: $!"
}

if [ "${AUTONOMY_ENABLED:-true}" = "true" ]; then
    start_optional_service "Scheduler" "python -c 'from agent.scheduler.task_scheduler import run_scheduler_loop; run_scheduler_loop()'"
    start_optional_service "Queue Consumer" "python -c 'import asyncio; from agent.interfaces.queue_consumer import run_consumer_loop; asyncio.run(run_consumer_loop())'"
fi

if [ "${TELEGRAM_POLLING_ENABLED:-false}" = "true" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    start_optional_service "Telegram Bot" "python -m agent.interfaces.telegram_bot"
else
    echo "Telegram polling deshabilitado (define TELEGRAM_POLLING_ENABLED=true para activarlo)"
fi

if [ -z "${SUPERDAPP_API_KEY:-}" ]; then
    echo "SUPERDAPP_API_KEY no configurado; no se puede iniciar webhook"
    exit 1
fi

port="${PORT:-8080}"
path="${SUPERDAPP_WEBHOOK_PATH:-/superdapp/webhook}"
echo "Superdapp Webhook listo en puerto ${port}, path ${path}"

# Proceso principal (critico): mantener en foreground para Railway.
exec python -m agent.interfaces.superdapp_bot
