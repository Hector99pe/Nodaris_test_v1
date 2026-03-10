"""Planner node for Nodaris agent.

Analyzes available data and creates a context-aware plan
that guides the agent_reasoner's tool selection.
"""

import json
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from langsmith import traceable

from agent.config import Config


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
        plan_parts.append(f"🔧 Análisis recomendados: {', '.join(recommended)}")

    elif mode == "individual":
        plan_parts.append(f"👤 DNI: {state.get('dni', 'N/A')}, Nota: {state.get('nota', 'N/A')}")

    plan_text = "\n".join(plan_parts)

    # Build initial message if none exists
    messages_update = []
    if not state.get("messages"):
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

    return {
        "plan": plan_text,
        "status": "planned",
        "mensaje": f"Plan de auditoría creado ({mode_text})",
        "messages": messages_update,
    }
