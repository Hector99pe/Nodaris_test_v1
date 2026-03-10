"""Planner node for Nodaris agent.

Analyzes available data and creates a context-aware plan
that guides the agent_reasoner's tool selection.
"""

import json
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from langsmith import traceable

from agent.config import Config
from agent.storage import AuditStore


def _reorder_by_learning(mode: str, recommended: list[str]) -> tuple[list[str], str]:
    """Prioritize recommended analyses using historical memory when available."""
    if not Config.LEARNING_MEMORY_ENABLED or not recommended:
        return recommended, ""

    try:
        profile = AuditStore().get_learning_profile(mode)
    except Exception:
        return recommended, ""

    ranked = profile.get("ranked_tools", [])
    if not ranked:
        return recommended, ""

    # Keep only tools suggested for this run, ordered by historical performance first.
    preferred = [tool for tool in ranked if tool in recommended]
    trailing = [tool for tool in recommended if tool not in preferred]
    final_tools = preferred + trailing

    hint = ", ".join(preferred[: Config.LEARNING_MEMORY_TOP_TOOLS])
    return final_tools, hint


@traceable(name="plannerNode")
def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Plan the audit by analyzing available data and building context.

    Inspects the state to determine:
    - What mode to operate in (individual, full exam, file)
    - What data is available
    - What initial guidance to provide

    The actual tool selection is delegated to agent_reasoner (LLM decides).

    Args:
        state: Current workflow state

    Returns:
        Updated state with plan and initial message
    """
    context = {
        "has_exam_data": bool(state.get("exam_data")),
        "has_students_data": bool(state.get("students_data")),
        "has_individual_data": bool(state.get("dni")),
        "has_file": bool(state.get("file_path")),
        "num_students": len(state.get("students_data", [])),
        "has_timing_data": False,
        "has_questions": False,
        "has_empty_responses": False,
    }

    students_data = state.get("students_data", [])
    exam_data = state.get("exam_data", {})

    # Analyze data characteristics
    if students_data:
        for student in students_data:
            if "tiempo_respuesta" in student or "tiempo_total" in student:
                context["has_timing_data"] = True
            respuestas = student.get("respuestas", [])
            if respuestas and any(r in ["NR", "", None] for r in respuestas):
                context["has_empty_responses"] = True

    if exam_data and "preguntas" in exam_data:
        context["has_questions"] = True
        context["num_questions"] = len(exam_data["preguntas"])

    # Determine mode
    if state.get("file_path"):
        mode = "file"
        mode_text = "Auditoría desde archivo"
        mode_icon = "📁"
    elif context["has_exam_data"] or context["has_students_data"]:
        mode = "full_exam"
        mode_text = "Auditoría de examen completo"
        mode_icon = "📊"
    elif context["has_individual_data"]:
        mode = "individual"
        mode_text = "Auditoría individual"
        mode_icon = "👤"
    else:
        mode = "conversational"
        mode_text = "Consulta conversacional"
        mode_icon = "💬"

    # Build plan description
    plan_parts = [
        f"{mode_icon} Modo: {mode_text}",
    ]

    if mode == "file":
        plan_parts.append(f"📂 Archivo: {state.get('file_path', 'N/A')}")
        plan_parts.append("📋 Pasos: extraer datos → interpretar estructura → normalizar → auditar")

    elif mode == "full_exam":
        plan_parts.append(f"👥 Estudiantes: {context['num_students']}")
        if context["has_questions"]:
            plan_parts.append(f"📝 Preguntas: {context.get('num_questions', 0)}")

        recommended = ["calcular_estadisticas"]
        if context["num_students"] >= 2:
            recommended.append("detectar_plagio")
        if context["has_empty_responses"]:
            recommended.append("analizar_abandono")
        if context["has_timing_data"]:
            recommended.append("analizar_tiempos")
        if context["has_questions"]:
            recommended.append("evaluar_dificultad")
        recommended, memory_hint = _reorder_by_learning(mode, recommended)
        plan_parts.append(f"🔧 Análisis recomendados: {', '.join(recommended)}")
        if memory_hint:
            plan_parts.append(f"🧠 Prioridad por histórico: {memory_hint}")

    elif mode == "individual":
        plan_parts.append(f"👤 DNI: {state.get('dni', 'N/A')}, Nota: {state.get('nota', 'N/A')}")

    # Detect re-planning (reflection has already happened at least once)
    is_replan = state.get("iteration_count", 0) > 0
    reflection_notes = state.get("reflection_notes", "") if is_replan else ""
    replan_num = state.get("iteration_count", 1) if is_replan else 0

    if is_replan:
        plan_parts.insert(0, f"🔄 Re-planificación #{replan_num}")
        if reflection_notes:
            plan_parts.append(f"📋 Motivo: {reflection_notes}")

    plan_text = "\n".join(plan_parts)

    # Build message for the LLM
    messages_update = []
    if not state.get("messages"):
        # First run: inject initial task message
        if mode == "file":
            msg = f"Necesito auditar los datos del archivo: {state.get('file_path')}"
        elif mode == "full_exam":
            exam_id = exam_data.get("examen", {}).get("id", "N/A") if exam_data else "N/A"
            msg = state.get("usuario_query", f"Audita el examen {exam_id} con {context['num_students']} estudiantes")
        elif mode == "individual":
            msg = state.get("usuario_query", f"Audita el registro: DNI {state.get('dni')}, Nota {state.get('nota')}")
        else:
            msg = state.get("usuario_query", "Consulta de auditoría académica")
        messages_update.append(HumanMessage(content=msg))
    elif is_replan and reflection_notes:
        # Re-plan run: inject reflection feedback so the LLM adjusts its strategy
        messages_update.append(HumanMessage(
            content=(
                f"[Re-planificación #{replan_num}] El análisis anterior fue insuficiente. "
                f"{reflection_notes}. "
                "Ajusta tu enfoque y ejecuta los análisis que falten."
            )
        ))

    label = f"Re-planificación #{replan_num} ({mode_text})" if is_replan else f"Plan de auditoría creado ({mode_text})"
    return {
        "plan": plan_text,
        "status": "planned",
        "mensaje": label,
        "messages": messages_update,
    }
