"""Tool for evaluating exam difficulty."""

import json
from enum import Enum
from typing import Annotated

from langchain_core.tools import tool as langgraph_tool
from langgraph.prebuilt import InjectedState


class DifficultyLevel(Enum):
    """Difficulty levels for academic content."""

    FACIL = "fácil"
    MEDIO = "medio"
    DIFICIL = "difícil"
    MUY_DIFICIL = "muy_difícil"


# === LangGraph Tool Wrapper ===

@langgraph_tool
def tool_evaluar_dificultad(
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Evalúa la dificultad de las preguntas del examen basándose en las respuestas de los estudiantes.

    Calcula el porcentaje de acierto por pregunta para determinar dificultad real.
    Requiere datos del examen con preguntas y respuestas de estudiantes.
    """
    state = state or {}
    exam_data = state.get("exam_data", {})
    students_data = state.get("students_data", [])

    preguntas = exam_data.get("preguntas", []) if exam_data else []
    if not preguntas or not students_data:
        return json.dumps({"tipo": "dificultad", "preguntas_dificiles": 0, "mensaje": "No hay datos suficientes"})

    correctas = [str(p.get("correcta", "")).upper() for p in preguntas if isinstance(p, dict)]
    stats_preguntas = []

    for idx, correcta in enumerate(correctas):
        aciertos = 0
        total = 0
        for student in students_data:
            respuestas = student.get("respuestas", [])
            if idx < len(respuestas):
                total += 1
                if str(respuestas[idx]).upper() == correcta:
                    aciertos += 1
        tasa = (aciertos / total * 100) if total > 0 else 0
        nivel = (
            DifficultyLevel.FACIL.value if tasa >= 80
            else DifficultyLevel.MEDIO.value if tasa >= 50
            else DifficultyLevel.DIFICIL.value if tasa >= 25
            else DifficultyLevel.MUY_DIFICIL.value
        )
        stats_preguntas.append({
            "pregunta": idx + 1,
            "tasa_acierto": round(tasa, 1),
            "nivel": nivel,
            "tema": preguntas[idx].get("tema", "N/A") if idx < len(preguntas) else "N/A"
        })

    dificiles = [p for p in stats_preguntas if p["nivel"] in [DifficultyLevel.DIFICIL.value, DifficultyLevel.MUY_DIFICIL.value]]

    return json.dumps({
        "tipo": "dificultad",
        "detalle_preguntas": stats_preguntas,
        "preguntas_dificiles": len(dificiles),
        "total_preguntas": len(correctas),
    }, ensure_ascii=False)
