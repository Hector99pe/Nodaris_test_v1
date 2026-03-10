"""Nodaris Academic Audit Agent - LangGraph workflow.

5-Layer Architecture:
    Layer 1: INTERFACES (telegram_bot.py, api_interface.py)
    Layer 2: PLANNER IA (planner_node)
    Layer 3: ANALYSIS NODES (validation, analysis, verification)
    Layer 4: TOOLS (crypto, prompts, dificultad, copia, tiempos, validacion)
    Layer 5: REPORT + MEMORY (report_node, memory_manager)

Workflow:
    User/API/Telegram → Planner → [Validation → Analysis → Verification]
    → Reflection → Report → Memory/Storage

Mission:
    Auditar resultados académicos y generar registros verificables.

Capabilities:
    - Planificar auditorías con IA
    - Validar datos académicos
    - Analizar con LLM (OpenAI)
    - Detectar anomalías
    - Reflexionar sobre resultados
    - Generar reportes profesionales
    - Generar hash de verificación

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
    from agent.nodes import (
        planner_node,
        validate_academic_data,
        analyze_with_llm,
        generate_verification,
        reflection_node,
        report_node
    )
except ModuleNotFoundError:
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from state import AcademicAuditState, Context
    from nodes import (
        planner_node,
        validate_academic_data,
        analyze_with_llm,
        generate_verification,
        reflection_node,
        report_node
    )


def should_continue_after_validation(state: AcademicAuditState) -> str:
    """Route based on validation status.

    Args:
        state: Current workflow state

    Returns:
        Next node name or END
    """
    if state.status == "error":
        return END
    return "analyze"


def should_continue_after_reflection(state: AcademicAuditState) -> str:
    """Route after reflection node.

    Args:
        state: Current workflow state

    Returns:
        Next node name
    """
    # Could add logic to retry analysis if reflection finds issues
    # For now, always proceed to report
    return "report"


# ============================================================================
# LAYER 2: Build the 5-Layer Architecture Workflow
# ============================================================================

workflow = StateGraph(AcademicAuditState, context_schema=Context)

# LAYER 2: PLANNER IA
workflow.add_node("planner", planner_node)

# LAYER 3: ANALYSIS NODES
workflow.add_node("validate", validate_academic_data)
workflow.add_node("analyze", analyze_with_llm)
workflow.add_node("verify", generate_verification)

# LAYER 5: REFLECTION & REPORT
workflow.add_node("reflection", reflection_node)
workflow.add_node("report", report_node)

# ============================================================================
# Define Workflow Edges (5-Layer Flow)
# ============================================================================

# Entry: Start → Planner
workflow.add_edge("__start__", "planner")

# Layer 2 → Layer 3: Planner → Validation
workflow.add_edge("planner", "validate")

# Layer 3: Analysis Pipeline
workflow.add_conditional_edges(
    "validate",
    should_continue_after_validation,
    {
        "analyze": "analyze",
        END: END,
    },
)
workflow.add_edge("analyze", "verify")

# Layer 3 → Layer 5: Verification → Reflection
workflow.add_edge("verify", "reflection")

# Layer 5: Reflection → Report
workflow.add_conditional_edges(
    "reflection",
    should_continue_after_reflection,
    {
        "report": "report",
    }
)

# Exit: Report → End
workflow.add_edge("report", END)

# Compile graph
graph = workflow.compile(name="Nodaris Academic Auditor")
