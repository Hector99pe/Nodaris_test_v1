# Guía Paso a Paso para Poner en Funcionamiento Todo el Agente IA (Nodaris)

Esta guía te deja Nodaris operativo de extremo a extremo en Windows:

- Modo manual con LangGraph Studio
- Bot de Telegram
- Modo autónomo (scheduler + consumer)

## 1. Requisitos previos

- Windows con PowerShell
- Python 3.10 o superior
- Acceso a internet
- Clave de OpenAI activa
- (Opcional) Token de bot de Telegram

Verifica Python:

```powershell
python --version
```

## 2. Ubicarte en el proyecto

En PowerShell:

```powershell
cd C:\Users\hpere\Desktop\Area_de_trabajo\Trabajos\Nodaris\Nodaris
```

## 3. Crear y activar entorno virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea scripts:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Instalar dependencias del proyecto

```powershell
python -m pip install --upgrade pip
pip install -e . "langgraph-cli[inmem]"
```

## 5. Configurar variables de entorno

1. Crea el archivo .env a partir de .env.example:

```powershell
Copy-Item .env.example .env
```

2. Edita .env y define como mínimo:

```text
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

3. Opcionales recomendadas:

```text
TELEGRAM_BOT_TOKEN=...
LANGSMITH_TRACING=false
AUTONOMY_ENABLED=true
```

## 6. Validar salud del sistema

Antes de arrancar, ejecuta:

```powershell
python -m agent.interfaces.health_check
```

Si quieres salida en JSON:

```powershell
python -m agent.interfaces.health_check --json
```

## 7. Arranque en modo manual (LangGraph Studio)

```powershell
langgraph dev
```

Luego abre en navegador:

- http://localhost:3000

Con esto puedes probar flujos conversacionales y auditorías directamente.

## 8. Arranque del bot de Telegram

En otra terminal (con el mismo entorno virtual activo):

```powershell
python -m agent.interfaces.telegram_bot
```

Comandos útiles dentro de Telegram:

- /start
- /help
- /auditar 12345678 15
- /auditorias
- /reporte 50
- /reporte examen EX-TEST-004
- /reporte dni 73333444
- /reporte alumno Javier
- /revision
- /stats
- /estado

## 9. Arranque del modo autónomo completo

Para procesamiento automático por lotes, usa 2 terminales adicionales:

### Terminal A: Scheduler (descubre archivos y crea jobs)

```powershell
python -m agent.scheduler.task_scheduler
```

### Terminal B: Consumer (ejecuta auditorías)

```powershell
python -m agent.interfaces.queue_consumer
```

## 10. Flujo de archivos del modo autónomo

1. Coloca archivos de entrada en:
   - data/inbox/
2. El scheduler los detecta y encola.
3. El consumer procesa y mueve resultados a:
   - data/processed/ (procesados correctamente)
   - data/review/ (requiere revisión manual)
   - data/failed/ (fallos definitivos)

## 11. Verificación funcional rápida

### Pruebas unitarias

```powershell
pytest tests/unit_tests/
```

### Pruebas de integración

```powershell
pytest tests/integration_tests/
```

## 12. Operación recomendada diaria

1. Activar entorno virtual.
2. Ejecutar health check.
3. Levantar langgraph dev (si usarás modo manual).
4. Levantar telegram_bot (si usarás canal Telegram).
5. Levantar scheduler + consumer (si usarás modo autónomo).
6. Monitorear /stats y /estado en Telegram.
7. Revisar carpeta data/review/ y resolver casos pendientes.

## 13. Solución de problemas frecuentes

### Error de clave OpenAI

- Revisa OPENAI_API_KEY en .env.
- Ejecuta de nuevo el health check.

### Bot Telegram no responde

- Verifica TELEGRAM_BOT_TOKEN.
- Asegúrate de que no haya otra instancia activa del bot.

### No se procesan archivos en autonomía

- Verifica AUTONOMY_ENABLED=true.
- Confirma que scheduler y consumer estén corriendo en terminales separadas.
- Comprueba que existan archivos reales en data/inbox/.

### Dependencias o imports fallando

- Confirma que el entorno virtual está activo.
- Reinstala con pip install -e . "langgraph-cli[inmem]".

## 14. Comandos resumen (checklist rápido)

```powershell
cd C:\Users\hpere\Desktop\Area_de_trabajo\Trabajos\Nodaris\Nodaris
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e . "langgraph-cli[inmem]"
Copy-Item .env.example .env
python -m agent.interfaces.health_check
langgraph dev
python -m agent.interfaces.telegram_bot
python -m agent.scheduler.task_scheduler
python -m agent.interfaces.queue_consumer
```

Con esto queda operativo todo el Agente IA Nodaris de punta a punta.

## 15. Integración Superdapp (webhook)

Si vas a usar Superdapp como canal, agrega estas variables en `.env`:

```text
SUPERDAPP_API_KEY=...
SUPERDAPP_API_URL=https://api.superdapp.com
SUPERDAPP_WEBHOOK_SECRET=tu_secreto_fuerte
SUPERDAPP_WEBHOOK_PORT=8443
SUPERDAPP_WEBHOOK_PATH=/superdapp/webhook
SUPERDAPP_SEND_ENDPOINT=/messages
```

Levanta el servicio webhook:

```powershell
python -m agent.interfaces.superdapp_bot
```

Verificación local rápida:

```powershell
Invoke-RestMethod -Method GET http://localhost:8443/health
```

Para registrar en Superdapp:

- Webhook URL: `https://TU_DOMINIO_PUBLICO/superdapp/webhook`
- Método: `POST`
- Secreto: mismo valor de `SUPERDAPP_WEBHOOK_SECRET`

Payload mínimo recomendado:

```json
{
  "conversation_id": "conv_001",
  "message": "Hola Nodaris"
}
```

## 16. Despliegue en Railway

1. Crea un servicio en Railway y conecta este repositorio.
2. Usa como Start Command:

```text
python -m agent.interfaces.superdapp_bot
```

3. Carga variables de entorno (al menos):
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `SUPERDAPP_API_KEY`
   - `SUPERDAPP_API_URL`
   - `SUPERDAPP_WEBHOOK_SECRET`
   - `SUPERDAPP_WEBHOOK_PATH`
   - `SUPERDAPP_SEND_ENDPOINT`
4. Railway define `PORT` automáticamente. Nodaris lo prioriza sobre `SUPERDAPP_WEBHOOK_PORT`.
5. Registra el webhook final en Superdapp con la URL pública de Railway.

Smoke test después del deploy:

- `GET https://<tu-servicio>.up.railway.app/health` debe devolver `ok=true`
- `POST https://<tu-servicio>.up.railway.app/superdapp/webhook` con secreto correcto debe devolver `200`
- Con secreto incorrecto debe devolver `401`
