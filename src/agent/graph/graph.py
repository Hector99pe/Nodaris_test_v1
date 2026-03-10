"""Nodaris Academic Audit Agent - LangGraph agentic workflow.

Architecture:
    - Planner: Analyzes input and creates audit plan
    - Validator: Validates academic data
    - Agent Reasoner: LLM brain that decides which tools to call (ReAct loop)
    - Tool Executor: Executes tools selected by the agent
    - Reflection: Reviews quality and can trigger re-planning
    - Verification: Generates cryptographic hash
    - Report: Generates professional audit report

Flow:
    START → planner → validate
        → (error → END)
        → (ok → agent_reasoner ⇄ tool_executor)
        → reflection
            → (replan → agent_reasoner)
            → (ok → verify → report → END)
"""

from __future__ import annotations

import json as _json
from pathlib import Path
import sys
from typing import Any, cast

from langchain_core.messages import ToolMessage as _ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition

try:
    from agent.config import Config
    from agent.state import AcademicAuditState
    from agent.nodes import (
        planner_node,
        validate_academic_data,
        generate_verification,
        reflection_node,
        report_node,
    )
    from agent.nodes.agent_reasoner import agent_reasoner
    from agent.tools import AUDIT_TOOLS
except ModuleNotFoundError:
    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    from config import Config
    from state import AcademicAuditState
    from nodes import (
        planner_node,
        validate_academic_data,
        generate_verification,
        reflection_node,
        report_node,
    )
    from nodes.agent_reasoner import agent_reasoner
    from tools import AUDIT_TOOLS


# ============================================================================
# Routing Functions
# ============================================================================


def route_after_validation(state: AcademicAuditState) -> str:
    """Route based on validation status."""
    if state.get("status") == "error":
        return END
    return "agent_reasoner"


def route_after_reflection(state: AcademicAuditState) -> str:
    """Route after reflection - replan via planner if confidence is too low.

    Only goes to verify/report if there's actual audit data.
    Conversational mode and failed extractions skip verify/report.
    When confidence is low the full planner is re-invoked so the LLM
    receives an updated plan enriched with reflection feedback.
    """
    # Must have actual analyzed data to produce a meaningful report
    has_audit_data = bool(
        state.get("exam_data")
        or state.get("students_data")
        or state.get("dni")
    )

    if not has_audit_data:
        return END

    confidence = state.get("confidence_score", 1.0)
    iteration = state.get("iteration_count", 0)

    if confidence < 0.7 and iteration < Config.MAX_REFLECTION_REPLANS:
        return "planner"  # true re-planning: planner rebuilds context with reflection notes
    return "verify"


def route_after_planner(state: AcademicAuditState) -> str:
    """Skip validation on replanning runs — data is already valid.

    First run (iteration_count == 0): validate → agent_reasoner.
    Subsequent runs triggered by reflection: go straight to agent_reasoner.
    """
    if state.get("iteration_count", 0) > 0:
        return "agent_reasoner"
    return "validate"


def route_after_reasoner(state: AcademicAuditState) -> str:
    """Route after reasoner with a hard stop to avoid endless loops."""
    iteration = state.get("iteration_count", 0)
    if iteration >= Config.MAX_AGENT_ITERATIONS:
        return "__end__"
    return tools_condition(cast(dict[str, Any], state))


# ============================================================================
# Smart Tool Executor
# ============================================================================

_tool_node = ToolNode(AUDIT_TOOLS)


def smart_tool_executor(state: AcademicAuditState) -> AcademicAuditState:
    """Execute tools and inject file/normalization data into state.

    Wraps the standard ToolNode. After executing tools, scans results
    for file extraction or normalization data and injects it into the
    state so subsequent analysis tools can access it.
    """
    result = _tool_node.invoke(state)

    for msg in result.get("messages", []):
        if not isinstance(msg, _ToolMessage):
            continue
        if not isinstance(msg.content, str):
            continue
        try:
            data = _json.loads(msg.content)
        except (_json.JSONDecodeError, TypeError):
            continue

        tipo = data.get("tipo")
        if tipo not in ("archivo", "normalizacion"):
            continue

        # --- Handle "archivo" type (from tool_extraer_datos_archivo) ---
        if tipo == "archivo":
            datos = data.get("datos")
            if not isinstance(datos, dict):
                continue

            # Auto-parsed tabular data (Excel/CSV with recognized headers)
            if "students_data" in datos:
                result["students_data"] = datos["students_data"]
                if "exam_data" in datos:
                    result["exam_data"] = datos["exam_data"]
            # Full Nodaris JSON schema
            elif all(k in datos for k in ("examen", "preguntas", "estudiantes", "resultados")):
                from agent.nodes.validation import _normalize_exam_payload
                exam_d, students_d = _normalize_exam_payload({"exam_data": datos})
                if students_d:
                    result["exam_data"] = exam_d
                    result["students_data"] = students_d

        # --- Handle "normalizacion" type (from tool_normalizar_datos_examen) ---
        elif tipo == "normalizacion":
            students = data.get("students_data", [])
            if students:
                result["students_data"] = students
            datos = data.get("datos")
            if isinstance(datos, dict) and all(k in datos for k in ("examen", "preguntas")):
                from agent.nodes.validation import _normalize_exam_payload
                exam_d, students_d = _normalize_exam_payload({"exam_data": datos})
                if exam_d:
                    result["exam_data"] = exam_d
                if students_d:
                    result["students_data"] = students_d

    return result


# ============================================================================
# Build Agentic Workflow
# ============================================================================

workflow = StateGraph(AcademicAuditState)

# --- Nodes ---
workflow.add_node("planner", planner_node)
workflow.add_node("validate", validate_academic_data)
workflow.add_node("agent_reasoner", agent_reasoner)
workflow.add_node("tool_executor", smart_tool_executor)
workflow.add_node("reflection", reflection_node)
workflow.add_node("verify", generate_verification)
workflow.add_node("report", report_node)

# --- Edges ---

# Entry: START → Planner → (first run: validate | replan: agent_reasoner)
workflow.add_edge(START, "planner")
workflow.add_conditional_edges(
    "planner",
    route_after_planner,
    {"validate": "validate", "agent_reasoner": "agent_reasoner"},
)

# Validation: error → END, ok → agent loop
workflow.add_conditional_edges(
    "validate",
    route_after_validation,
    {"agent_reasoner": "agent_reasoner", END: END},
)

# Agent ReAct loop: agent_reasoner ⇄ tool_executor
workflow.add_conditional_edges(
    "agent_reasoner",
    route_after_reasoner,
    {"tools": "tool_executor", "__end__": "reflection"},
)
workflow.add_edge("tool_executor", "agent_reasoner")

# Reflection: replan → planner (true re-plan), conversational → END, audit → verify
workflow.add_conditional_edges(
    "reflection",
    route_after_reflection,
    {"planner": "planner", "verify": "verify", END: END},
)

# Final: verify → report → END
workflow.add_edge("verify", "report")
workflow.add_edge("report", END)

# --- Compile graph ---
# `graph`: No checkpointer — used by `langgraph dev` (which injects its own).
# `graph_with_memory`: MemorySaver checkpointer — used by Telegram bot / standalone.
graph = workflow.compile(
    name="Nodaris Academic Auditor",
)


def get_graph_with_memory():
    """Compile the workflow with an in-memory checkpointer for standalone use.

    When ALLOW_HUMAN_INTERRUPT=true the graph pauses *before* agent_reasoner
    on every iteration, allowing an external caller (e.g. Telegram bot) to
    inspect/modify state and then resume by invoking the graph again with
    the same thread_id.
    """
    from langgraph.checkpoint.memory import MemorySaver
    interrupt_nodes = ["agent_reasoner"] if Config.ALLOW_HUMAN_INTERRUPT else []
    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=interrupt_nodes or None,
        name="Nodaris Academic Auditor",
    )
