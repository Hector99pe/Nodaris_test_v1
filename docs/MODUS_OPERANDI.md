# Modus Operandi

Este documento describe como operar Nodaris en su implementacion actual.

## 1. Modos de entrada

Nodaris soporta cuatro modos:

- `conversational`: consultas generales sin ejecutar auditoria completa.
- `individual`: auditoria por `dni` y `nota`.
- `full_exam`: auditoria de examen completo con `exam_data` y/o `students_data`.
- `file`: auditoria desde archivo (`file_path`) con extraccion y normalizacion.

El modo lo determina `planner_node` en `src/agent/nodes/planner.py`.

## 2. Flujo operativo

1. Planner construye plan segun datos disponibles.
2. Validation normaliza/valida estructura y reglas base.
3. Agent reasoner decide herramientas a ejecutar.
4. Tool executor ejecuta herramientas y actualiza estado.
5. Reflection evalua cobertura y confianza.
6. Si confianza baja: replanificacion.
7. Si confianza suficiente: verificacion hash y reporte final.

## 3. Herramientas de auditoria

Catalogo activo en `src/agent/tools/__init__.py`:

- `calcular_estadisticas`
- `detectar_plagio`
- `analizar_abandono`
- `analizar_tiempos`
- `evaluar_dificultad`
- `generar_hash`
- `extraer_datos_archivo`
- `normalizar_datos_examen`
- `solicitar_clarificacion`

## 4. Operacion manual

### LangGraph local

```bash
langgraph dev
```

### Tests

```bash
python -m pytest tests/unit_tests/
python -m pytest tests/integration_tests/
```

### Telegram bot

Comandos principales:

- `/start`
- `/help`
- `/auditar <dni> <nota>`
- `/auditorias`
- `/stats`
- `/estado`

## 5. Operacion autonoma

### Discovery scheduler

```bash
python -m agent.scheduler.task_scheduler
```

Escanea `AUTONOMY_INBOX_PATH` y encola jobs en SQLite.

### Queue consumer

```bash
python -m agent.interfaces.queue_consumer
```

Consume jobs pendientes, ejecuta auditoria y mueve archivos a:

- `AUTONOMY_PROCESSED_PATH`
- `AUTONOMY_REVIEW_PATH`
- `AUTONOMY_FAILED_PATH`

### Herramientas de operacion

```bash
python -m agent.interfaces.health_check
python -m agent.interfaces.autonomy_status
python -m agent.interfaces.review_queue list
python -m agent.interfaces.dead_letter_queue list
```

## 6. Persistencia

`AuditStore` (`src/agent/storage/audit_store.py`) persiste:

- auditorias (`audits`)
- hallazgos (`findings`)
- cola (`audit_jobs`)
- memoria de aprendizaje (`agent_memory`)
- dead letters (`dead_letter_jobs`)

## 7. Guardrails

- Circuit breaker LLM.
- Limites de iteracion y replanificacion.
- Politicas de revision segun riesgo y confianza.
- Report guardrail para evitar secciones sin datos.
