"""Agent reasoner node for Nodaris.

The brain of the agentic loop. Uses ChatOpenAI with bound tools
to let the LLM decide which analyses to run and when to stop.
"""

import json
import logging
from typing import Any, Dict

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import SecretStr

from agent.config import Config
from agent.resilience import call_with_llm_circuit_breaker
from agent.tools import AUDIT_TOOLS
from agent.tools.prompts import build_agent_system_prompt

logger = logging.getLogger("nodaris.agent_reasoner")


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
        parts.append("## Datos del Examen")
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
        parts.append("## Auditoría Individual")
        parts.append(f"- DNI: {dni}")
        parts.append(f"- Nota: {nota}")

    file_path = state.get("file_path", "")
    if file_path and not exam_data:
        parts.append("## Archivo Pendiente")
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

    api_key = SecretStr(Config.OPENAI_API_KEY) if Config.OPENAI_API_KEY else None

    llm = ChatOpenAI(
        api_key=api_key,
        model=Config.OPENAI_MODEL,
        temperature=Config.OPENAI_TEMPERATURE,
    ).bind_tools(AUDIT_TOOLS)

    # Build the system prompt with current context
    context = _build_context(state)
    system_prompt = build_agent_system_prompt(context)
    system_msg = SystemMessage(content=system_prompt)

    # Get existing messages (filter out old system messages to avoid duplication)
    existing_messages = [
        m for m in state.get("messages", [])
        if not isinstance(m, SystemMessage)
    ]

    # Invoke LLM
    response = call_with_llm_circuit_breaker(
        lambda: llm.invoke([system_msg] + existing_messages)
    )

    iteration = state.get("iteration_count", 0) + 1

    has_tool_calls = bool(getattr(response, "tool_calls", None))
    logger.info("Reasoner iteration=%d, has_tool_calls=%s, model=%s", iteration, has_tool_calls, Config.OPENAI_MODEL)

    return {
        "messages": [response],
        "iteration_count": iteration,
    }
