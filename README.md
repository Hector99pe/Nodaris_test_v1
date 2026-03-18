# Nodaris - Agente de Auditoría Académica

**Nodaris** es un agente inteligente basado en LangGraph para auditar resultados académicos, detectar anomalías y generar reportes confiables con trazabilidad criptográfica.

## ¿Qué hace Nodaris?

- **Valida datos académicos**: DNI, notas, estructura de exámenes.
- **Detecta anomalías**: plagio entre estudiantes, abandono (NR), tiempos sospechosos.
- **Evalúa dificultad**: análisis de preguntas por tasa de acierto.
- **Genera reportes**: auditorías profesionales con hash SHA-256 verificable.
- **Funciona en modo autónomo**: procesa lotes de archivos con priorización y revisión manual.

## Inicio Rápido

### 1. Instalar dependencias

```bash
pip install -e . "langgraph-cli[inmem]"
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Mínimo requerido:

```text
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Opcional:

```text
TELEGRAM_BOT_TOKEN=...
LANGSMITH_TRACING=true
AUTONOMY_ENABLED=true
```

### 3. Ejecutar localmente

```bash
langgraph dev
```

Abre http://localhost:3000 en el navegador.

### 4. Ejecutar tests

```bash
pytest tests/unit_tests/
pytest tests/integration_tests/
```

## Modos de Operación

### Manual / Conversacional

Mediante interfaz LangGraph Studio o Telegram bot:

```
/auditar 12345678 15           # Auditoría individual
/auditorias                    # Listar recientes
/help                          # Ver comandos
```

### Autónomo

1. Coloca archivos en `data/inbox/`
2. Ejecuta scheduler:
   ```bash
   python -m agent.scheduler.task_scheduler
   ```
3. Ejecuta consumidor:
   ```bash
   python -m agent.interfaces.queue_consumer
   ```

Los archivos procesados se mueven a `data/processed/`, `data/review/` o `data/failed/`.

## Integración Superdapp

Nodaris soporta integración con Superdapp en dos vías:

- Entrada por webhook (eventos/mensajes entrantes)
- Salida por API REST (respuesta del asistente de vuelta a Superdapp)

Variables principales:

```text
SUPERDAPP_API_KEY=...
SUPERDAPP_API_URL=https://api.superdapp.com
SUPERDAPP_WEBHOOK_SECRET=... # usa un valor aleatorio fuerte
SUPERDAPP_WEBHOOK_PORT=8443
SUPERDAPP_WEBHOOK_PATH=/superdapp/webhook
SUPERDAPP_SEND_ENDPOINT=/messages
```

Levantar webhook local:

```bash
python -m agent.interfaces.superdapp_bot
```

Endpoints:

- Health: `GET /health`
- Webhook: `POST /superdapp/webhook` (o el path definido en `SUPERDAPP_WEBHOOK_PATH`)

Payload mínimo esperado:

```json
{
  "conversation_id": "conv_001",
  "message": "Hola Nodaris"
}
```

Registro en Superdapp:

- Webhook URL: `https://TU_DOMINIO_PUBLICO/superdapp/webhook`
- Método: `POST`
- Secreto: mismo valor que `SUPERDAPP_WEBHOOK_SECRET`

## Deploy en Railway

Configuración recomendada para desplegar solo la interfaz Superdapp:

1. Crea un servicio en Railway conectado a este repositorio.
2. Define Start Command:

   ```bash
   python -m agent.interfaces.superdapp_bot
   ```

3. Configura variables en Railway (Environment):
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `SUPERDAPP_API_KEY`
   - `SUPERDAPP_API_URL`
   - `SUPERDAPP_WEBHOOK_SECRET`
   - `SUPERDAPP_WEBHOOK_PATH`
   - `SUPERDAPP_SEND_ENDPOINT`
4. Railway inyecta `PORT` automáticamente. El servicio ya lo usa por configuración.
5. Registra en Superdapp la URL pública que entrega Railway:

   ```text
   https://<tu-servicio>.up.railway.app/superdapp/webhook
   ```

6. Smoke test post-deploy:
   - `GET /health` debe responder `ok: true`
   - `POST /superdapp/webhook` con secreto válido debe responder `200`
   - `POST /superdapp/webhook` con secreto inválido debe responder `401`

## Documentación

- [docs/README.md](./docs/README.md) - Índice de documentación
- [docs/ARQUITECTURA_5_CAPAS.md](./docs/ARQUITECTURA_5_CAPAS.md) - Flujo agentico y capas
- [docs/ESTRUCTURA.md](./docs/ESTRUCTURA.md) - Estructura del código
- [docs/MODUS_OPERANDI.md](./docs/MODUS_OPERANDI.md) - Cómo operar
- [docs/DATOS_ENTRADA.md](./docs/DATOS_ENTRADA.md) - Formatos soportados

## Stack

- **LangGraph**: Orquestación de flujos agenticos
- **OpenAI GPT-4o-mini**: LLM para análisis
- **Python 3.10+**: Lenguaje base
- **SQLite**: Persistencia de auditorías
- **Telegram Bot API**: Interfaz conversacional
- **LangSmith**: Tracing opcional

## Contacto / Issues

Abre un issue o pull request en el repositorio.
