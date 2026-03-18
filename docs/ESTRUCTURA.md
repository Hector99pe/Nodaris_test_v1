# Estructura del Proyecto

Estructura real del repositorio (actualizada).

## Raiz

- `src/agent/`: implementacion principal del agente.
- `tests/`: pruebas unitarias e integracion.
- `data/`: bandejas de entrada/salida para ejecucion autonoma y datasets de ejemplo.
- `docs/`: documentacion tecnica del proyecto.
- `langgraph.json`: entrada oficial para `langgraph dev`.

## src/agent

```text
src/agent/
  config/
    config.py                 # Variables de entorno y limites operativos
  graph/
    graph.py                  # Grafo LangGraph y ruteo condicional
  state/
    state.py                  # AcademicAuditState (TypedDict)
  nodes/
    planner.py                # Planificacion por contexto y aprendizaje historico
    validation.py             # Validacion y normalizacion de payloads
    agent_reasoner.py         # LLM con herramientas (ReAct)
    reflection.py             # Cobertura, confianza y feedback de replanificacion
    verification.py           # Hash verificable
    report.py                 # Reporte final y persistencia
    discovery.py              # Descubrimiento de archivos para cola autonoma
    risk_scoring.py           # Priorizacion/riesgo de archivos
  tools/
    validacion.py             # Estadisticas y distribucion de notas
    detectar_copia.py         # Deteccion de similitud entre estudiantes
    analizar_abandono.py      # Deteccion de NR/abandono
    tiempos.py                # Tiempos sospechosos
    dificultad.py             # Dificultad por pregunta
    file_parser.py            # Extraccion/normalizacion desde CSV/JSON
    crypto.py                 # Hashes y utilidades criptograficas
    prompts.py                # Prompt system para el reasoner
  interfaces/
    telegram_bot.py           # Bot Telegram y comandos de operacion
    health_check.py           # Diagnostico global
    queue_consumer.py         # Consumidor de trabajos en cola
    autonomy_status.py        # Estado rapido de cola autonoma
    review_queue.py           # Gestion de jobs en revision
    dead_letter_queue.py      # Gestion de dead letters
  scheduler/
    task_scheduler.py         # Discovery periodico
  storage/
    audit_store.py            # Persistencia SQLite
  conversation.py             # Adaptador conversacional al grafo con memoria
  resilience.py               # Circuit breaker y reintentos LLM
```

## tests

- `tests/unit_tests/`: validacion de planner, colas, salud, resiliencia y politicas.
- `tests/integration_tests/test_graph.py`: prueba e2e del flujo con dataset de anomalias.

## data

- `data/inbox/`: archivos nuevos para discovery.
- `data/processed/`: jobs completados automaticamente.
- `data/review/`: jobs enviados a revision manual.
- `data/failed/` (si aplica): archivos fallidos tras agotar reintentos.
