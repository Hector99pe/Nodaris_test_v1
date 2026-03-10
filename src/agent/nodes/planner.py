"""Planner node for Nodaris agent.

Analyzes user queries and data to create execution plans.
Decides which analysis to run based on available data.
"""

import json
from typing import cast

from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import SecretStr

from agent.state import AcademicAuditState
from agent.config import Config

# Initialize LLM for intelligent planning
api_key = SecretStr(Config.OPENAI_API_KEY) if Config.OPENAI_API_KEY else None
llm = ChatOpenAI(
    model=Config.OPENAI_MODEL,
    temperature=0.0,  # Deterministic for planning
    api_key=api_key,
)


@traceable(name="plannerNode")
def planner_node(state: AcademicAuditState) -> AcademicAuditState:
    """Plan the execution workflow using LLM reasoning.

    Uses ChatOpenAI to intelligently decide which analyses to run based on:
    - Available data (exam_data, students_data, dni/nota)
    - Data characteristics (number of students, timing info, etc.)
    - Audit objectives

    Args:
        state: Current workflow state

    Returns:
        Updated state with execution plan and analysis_to_run
    """
    # Build context for LLM
    context = {
        "has_exam_data": bool(state.exam_data),
        "has_students_data": bool(state.students_data),
        "has_individual_data": bool(state.dni),
        "num_students": len(state.students_data) if state.students_data else 0,
        "has_timing_data": False,
        "has_questions": False,
        "has_empty_responses": False
    }

    # Analyze data characteristics
    if state.students_data:
        for student in state.students_data:
            if "tiempo_respuesta" in student or "tiempo_total" in student:
                context["has_timing_data"] = True
            respuestas = student.get("respuestas", [])
            if respuestas and any(r in ["NR", "", None] for r in respuestas):
                context["has_empty_responses"] = True

    if state.exam_data and "preguntas" in state.exam_data:
        context["has_questions"] = True
        context["num_questions"] = len(state.exam_data["preguntas"])

    # Build LLM prompt
    prompt = f"""You are an intelligent academic audit planner. Analyze the context and decide which analyses should run.

**Available Analyses:**
- validation: Validate data structure and integrity
- basic_statistics: Calculate basic exam statistics
- grade_analysis: Analyze grade distribution
- detectar_copia: Detect plagiarism between students (requires ≥2 students)
- analizar_abandono: Analyze student abandonment (NR/empty responses)
- analizar_tiempos: Analyze suspicious timing patterns
- evaluar_dificultad: Evaluate question difficulty
- individual_analysis: Individual student audit

**Context:**
{json.dumps(context, indent=2)}

**Rules:**
1. Always include "validation" first
2. For full exam audits (has_exam_data or has_students_data): include basic_statistics and grade_analysis
3. Only include detectar_copia if num_students >= 2
4. Only include analizar_abandono if has_empty_responses is true
5. Only include analizar_tiempos if has_timing_data is true
6. Only include evaluar_dificultad if has_questions is true
7. For individual audits (has_individual_data only): include individual_analysis

**Output Format (JSON only):**
{{
  "mode": "full_exam" or "individual",
  "analysis_to_run": ["list", "of", "analyses"],
  "reasoning": "brief explanation"
}}

Respond with valid JSON only, no markdown formatting."""

    try:
        # Invoke LLM
        response = llm.invoke(prompt)
        content = response.content

        if isinstance(content, str):
            response_text = content.strip()
        else:
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    maybe_text = item.get("text")
                    if isinstance(maybe_text, str):
                        text_parts.append(maybe_text)
            response_text = "".join(text_parts).strip()

        # Clean markdown formatting if present
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()

        # Parse LLM response
        plan_data = cast(dict[str, object], json.loads(response_text))

        raw_analysis = plan_data.get("analysis_to_run", ["validation"])
        analysis_to_run = [item for item in raw_analysis if isinstance(item, str)] if isinstance(raw_analysis, list) else ["validation"]

        raw_mode = plan_data.get("mode", "unknown")
        mode = raw_mode if isinstance(raw_mode, str) else "unknown"

        raw_reasoning = plan_data.get("reasoning", "Plan generado por IA")
        reasoning = raw_reasoning if isinstance(raw_reasoning, str) else "Plan generado por IA"

        # Build plan description
        mode_icon = "📊" if mode == "full_exam" else "👤"
        mode_text = "Auditoría de examen completo" if mode == "full_exam" else "Auditoría individual"

        plan_description = [
            f"{mode_icon} Modo: {mode_text}",
            f"🤖 Razonamiento IA: {reasoning}",
            f"📋 Análisis a ejecutar: {', '.join(analysis_to_run)}"
        ]

        # Add context details
        if context["num_students"] > 0:
            plan_description.insert(1, f"👥 Estudiantes: {context['num_students']}")
        if context["has_questions"]:
            plan_description.insert(1, f"📝 Preguntas: {context.get('num_questions', 0)}")

    except Exception as e:
        # Fallback to rule-based planning if LLM fails
        analysis_to_run = ["validation"]
        plan_description = [
            "⚠️ Fallback a planeación basada en reglas",
            f"Error LLM: {str(e)[:50]}"
        ]

        # Simple rule-based fallback
        if state.exam_data or state.students_data:
            analysis_to_run.extend(["basic_statistics", "grade_analysis"])
            if context["num_students"] >= 2:
                analysis_to_run.append("detectar_copia")
        else:
            analysis_to_run.append("individual_analysis")

    # Build plan description
    plan_text = "\n".join(plan_description)

    # Update state
    state.plan = plan_text
    state.analysis_to_run = analysis_to_run
    state.status = "planned"
    state.mensaje = f"Plan de auditoría creado con {len(analysis_to_run)} análisis"

    return state
