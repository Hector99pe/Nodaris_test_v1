"""Agent reasoner node for Nodaris.

The brain of the agentic loop. Uses ChatOpenAI with bound tools
to let the LLM decide which analyses to run and when to stop.
"""

import json
from typing import Any, Dict

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable

from agent.config import Config
from agent.tools import AUDIT_TOOLS


AGENT_SYSTEM_PROMPT = """Eres Nodaris, un agente experto en auditoría académica.

## Tu Misión
Auditar resultados académicos y generar registros verificables con trazabilidad criptográfica.

## Cómo Operas
1. Analiza el contexto y los datos disponibles
2. Usa tus herramientas para realizar análisis específicos
3. Evalúa los resultados de cada herramienta
4. Decide si necesitas más análisis o si tienes suficiente información
5. Cuando tengas suficiente información, genera un resumen claro de hallazgos

## Herramientas Disponibles
- **tool_calcular_estadisticas**: Calcula promedios, distribución de notas, nota máxima/mínima
- **tool_detectar_plagio**: Compara respuestas entre estudiantes para detectar copias
- **tool_analizar_abandono**: Identifica estudiantes que no respondieron (NR)
- **tool_analizar_tiempos**: Detecta tiempos de respuesta sospechosamente cortos
- **tool_evaluar_dificultad**: Evalúa dificultad real de cada pregunta
- **tool_generar_hash**: Genera hash SHA-256 para verificación individual
- **tool_extraer_datos_archivo**: Extrae datos de archivos Excel/PDF/JSON
- **tool_normalizar_datos_examen**: Normaliza datos a formato estándar
- **tool_solicitar_clarificacion**: Pregunta al usuario si algo no está claro

## Escala de Notas (0-20)
- 0-10: Desaprobado
- 11-13: Aprobado
- 14-16: Bueno
- 17-18: Muy bueno
- 19-20: Excelente

## Reglas
- SIEMPRE usa herramientas cuando haya datos que analizar. No inventes resultados.
- Para exámenes completos: empieza con estadísticas, luego detección de anomalías.
- Si hay 2+ estudiantes, SIEMPRE ejecuta detección de plagio.
- Si los datos son ambiguos, usa tool_solicitar_clarificacion para preguntar.
- Cuando termines todos los análisis, responde con un resumen estructurado.
- Sé profesional, conciso y accionable en español.
- NO repitas herramientas que ya ejecutaste salvo que tengas razón específica.

## Contexto Actual
{context}"""


def _build_context(state: Dict[str, Any]) -> str:
    """Build context string from current state for the system prompt."""
    parts = []

    plan = state.get("plan", "")
    if plan:
        parts.append(f"## Plan de Auditoría\n{plan}")

    exam_data = state.get("exam_data", {})
    if exam_data:
        examen = exam_data.get("examen", {})
        preguntas = exam_data.get("preguntas", [])
        parts.append(f"## Datos del Examen")
        parts.append(f"- ID: {examen.get('id', 'N/A')}")
        parts.append(f"- Curso: {examen.get('curso', 'N/A')}")
        parts.append(f"- Preguntas: {len(preguntas)}")
        parts.append(f"- Duración: {examen.get('duracion_min', 'N/A')} min")

    students = state.get("students_data", [])
    if students:
        parts.append(f"- Estudiantes: {len(students)}")

    dni = state.get("dni", "")
    if dni:
        nota = state.get("nota", -1)
        parts.append(f"## Auditoría Individual")
        parts.append(f"- DNI: {dni}")
        parts.append(f"- Nota: {nota}")

    file_path = state.get("file_path", "")
    if file_path and not exam_data:
        parts.append(f"## Archivo Pendiente")
        parts.append(f"- Ruta: {file_path}")
        parts.append(f"- Tipo: {state.get('file_type', 'desconocido')}")

    return "\n".join(parts) if parts else "No hay contexto adicional."


@traceable(name="agentReasoner")
def agent_reasoner(state: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke the LLM with bound tools to reason about next actions.

    The LLM sees the full conversation history and decides whether to:
    - Call tools for more analysis
    - Respond with a summary (no tool calls → exit loop)

    Args:
        state: Current graph state

    Returns:
        Updated state with new message(s) and incremented iteration count
    """
    if not Config.OPENAI_API_KEY:
        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content="Error: OPENAI_API_KEY no configurada")],
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    llm = ChatOpenAI(
        api_key=Config.OPENAI_API_KEY,
        model=Config.OPENAI_MODEL,
        temperature=Config.OPENAI_TEMPERATURE,
    ).bind_tools(AUDIT_TOOLS)

    # Build the system prompt with current context
    context = _build_context(state)
    system_prompt = AGENT_SYSTEM_PROMPT.replace("{context}", context)
    system_msg = SystemMessage(content=system_prompt)

    # Get existing messages (filter out old system messages to avoid duplication)
    existing_messages = [
        m for m in state.get("messages", [])
        if not isinstance(m, SystemMessage)
    ]

    # Invoke LLM
    response = llm.invoke([system_msg] + existing_messages)

    iteration = state.get("iteration_count", 0) + 1

    return {
        "messages": [response],
        "iteration_count": iteration,
    }
