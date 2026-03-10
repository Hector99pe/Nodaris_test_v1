"""Nodaris Academic Audit Agent - LangGraph workflow.

Mission:
    Auditar resultados académicos y generar registros verificables.

Capabilities:
    - Validar datos académicos
    - Analizar con LLM (OpenAI)
    - Detectar anomalías
    - Generar hash de verificación

Interface:
    LangGraph API → Future: Telegram chatbot

Environment:
    Instituciones educativas
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import sys

from langgraph.graph import StateGraph, END
from langgraph.runtime import Runtime

# Import with fallback for local development
try:
    from agent.state import AcademicAuditState, Context
    from agent.nodes import validate_academic_data, analyze_with_llm, generate_verification
except ModuleNotFoundError:
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from state import AcademicAuditState, Context
    from nodes import validate_academic_data, analyze_with_llm, generate_verification


def should_continue(state: AcademicAuditState) -> str:
    """Route based on validation status.

    Args:
        state: Current workflow state

    Returns:
        Next node name or END
    """
    if state.status == "error":
        return END
    return "analyze"


# Build the workflow graph
workflow = StateGraph(AcademicAuditState, context_schema=Context)

# Add nodes
workflow.add_node("validate", validate_academic_data)
workflow.add_node("analyze", analyze_with_llm)
workflow.add_node("verify", generate_verification)

# Define edges
workflow.add_edge("__start__", "validate")
workflow.add_conditional_edges(
    "validate",
    should_continue,
    {
        "analyze": "analyze",
        END: END,
    },
)
workflow.add_edge("analyze", "verify")
workflow.add_edge("verify", END)

# Compile graph
graph = workflow.compile(name="Nodaris Academic Auditor")
