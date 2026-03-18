# Arquitectura de 5 Capas - Nodaris

Documento actualizado segun el codigo real en `src/agent/`.

## Vista General

Nodaris usa un flujo agentico en LangGraph con ciclo ReAct:

1. Planner
2. Validation (solo en primera pasada)
3. Agent Reasoner + Tool Executor (bucle)
4. Reflection (calidad y cobertura)
5. Verification + Report

## Flujo del Grafo

Implementado en `src/agent/graph/graph.py`.

```text
START -> planner
planner -> validate (primera ejecucion) | agent_reasoner (replan)
validate -> END (error) | agent_reasoner
agent_reasoner -> tool_executor -> agent_reasoner (mientras haya tool calls)
agent_reasoner -> reflection (cuando ya no pide herramientas)
reflection -> planner (si baja confianza) | verify | END
verify -> report -> END
```

## Capa 1 - Interfaces

Ubicacion: `src/agent/interfaces/`

- `telegram_bot.py`: interfaz conversacional y comandos operativos.
- `health_check.py`: chequeo integral de configuracion y colas.
- `autonomy_status.py`: estado de cola autonoma.
- `review_queue.py`: decisiones manuales sobre jobs en revision.
- `dead_letter_queue.py`: inspeccion y reencolado de dead letters.
- `queue_consumer.py`: consumidor de trabajos autonomos.

## Capa 2 - Planner

Ubicacion: `src/agent/nodes/planner.py`

Responsabilidades:

- Determinar modo: `conversational`, `individual`, `full_exam`, `file`.
- Construir un plan textual para el reasoner.
- Sugerir herramientas segun contexto de datos.
- Aplicar priorizacion por memoria historica (`agent_memory`).
- En replanificacion, inyectar feedback de reflexion.

## Capa 3 - Analisis Agentico

Ubicacion: `src/agent/nodes/agent_reasoner.py` + `src/agent/graph/graph.py`

Responsabilidades:

- `agent_reasoner`: LLM con `bind_tools(AUDIT_TOOLS)` decide siguiente accion.
- `smart_tool_executor`: ejecuta herramientas, inyecta datos normalizados al estado,
  maneja hints de recuperacion y cachea resultados repetidos.
- Control de iteraciones: `MAX_AGENT_ITERATIONS`.

## Capa 4 - Tools

Ubicacion: `src/agent/tools/`

Catalogo principal (`AUDIT_TOOLS`):

- `tool_calcular_estadisticas`
- `tool_detectar_plagio`
- `tool_analizar_abandono`
- `tool_analizar_tiempos`
- `tool_evaluar_dificultad`
- `tool_generar_hash`
- `tool_extraer_datos_archivo`
- `tool_normalizar_datos_examen`
- `tool_solicitar_clarificacion`

## Capa 5 - Reflection, Verification y Reporte

Ubicacion: `src/agent/nodes/reflection.py`, `src/agent/nodes/verification.py`, `src/agent/nodes/report.py`

Responsabilidades:

- `reflection`: extrae hallazgos desde ToolMessages, calcula cobertura y confianza,
  puede forzar replanificacion.
- `verification`: genera hash verificable del payload auditado.
- `report`: construye reporte final, aplica guardrails y persiste auditoria.

## Persistencia y Autonomia

Ubicacion: `src/agent/storage/audit_store.py`, `src/agent/nodes/discovery.py`, `src/agent/scheduler/task_scheduler.py`

- Persistencia SQLite para auditorias, findings, jobs, memoria de aprendizaje y dead letters.
- Discovery de archivos (`data/inbox`) con `risk_scoring` para priorizar jobs.
- Scheduler y consumer para ejecucion autonoma por lotes.

## Guardrails Activos

- Circuit breaker para llamadas LLM (`src/agent/resilience.py`).
- Limite de iteraciones de agente y de replans de reflexion.
- Report guardrail para eliminar secciones sin respaldo de datos.
- Politicas de revision manual para jobs de riesgo/alta incertidumbre.
- **Configuration:** [`src/agent/config/config.py`](../src/agent/config/config.py)

## 🔍 Testing del Flujo

Para probar el flujo completo:

```python
from agent.graph import graph
from agent.state import AcademicAuditState

# Crear estado inicial
state = AcademicAuditState(
    dni="12345678",
    nota=15
)

# Ejecutar el grafo
result = graph.invoke(state)

# El resultado pasa por:
# planner → validate → analyze → verify → reflection → report
```

## 📊 Métricas de Arquitectura

- **Total de Capas:** 5
- **Total de Nodos:** 6 (planner, validate, analyze, verify, reflection, report)
- **Total de Tools:** 6
- **Total de Interfaces:** 2 (Telegram + API)
- **Puntos de Decisión:** 2 (después de validation y reflection)

---

**Última Actualización:** 9 de marzo de 2026
**Versión:** 2.0 (Arquitectura de 5 Capas)
