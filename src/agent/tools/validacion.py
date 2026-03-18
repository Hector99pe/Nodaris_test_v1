"""Tool for calculating exam statistics."""

import json
from typing import Annotated

from langchain_core.tools import tool as langgraph_tool
from langgraph.prebuilt import InjectedState

# === LangGraph Tool Wrappers ===

@langgraph_tool
def tool_calcular_estadisticas(
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Calcula estadísticas del examen: notas individuales, promedio, y distribución.

    Usa las respuestas correctas para calcular nota de cada estudiante.
    Genera distribución por rangos: 0-10, 11-13, 14-16, 17-20.
    """
    state = state or {}
    exam_data = state.get("exam_data", {})
    students_data = state.get("students_data", [])

    preguntas = exam_data.get("preguntas", []) if exam_data else []
    correctas = [str(p.get("correcta", "")).upper() for p in preguntas if isinstance(p, dict)]

    if not correctas or not students_data:
        return json.dumps({"tipo": "estadisticas", "promedio": 0, "mensaje": "Datos insuficientes"})

    notas = []
    for student in students_data:
        respuestas = student.get("respuestas", [])
        aciertos = sum(
            1 for i, r in enumerate(respuestas[:len(correctas)])
            if str(r).upper() == correctas[i]
        )
        nota_20 = round((aciertos / len(correctas)) * 20, 2) if correctas else 0
        notas.append({"dni": student.get("dni", ""), "nota": nota_20, "aciertos": aciertos})

    valores = [n["nota"] for n in notas]
    promedio = round(sum(valores) / len(valores), 2) if valores else 0.0

    distribucion = {
        "0-10": sum(1 for v in valores if v <= 10),
        "11-13": sum(1 for v in valores if 11 <= v <= 13),
        "14-16": sum(1 for v in valores if 14 <= v <= 16),
        "17-20": sum(1 for v in valores if v >= 17),
    }

    return json.dumps({
        "tipo": "estadisticas",
        "promedio": promedio,
        "distribucion": distribucion,
        "notas_individuales": notas,
        "total_estudiantes": len(notas),
        "nota_maxima": max(valores) if valores else 0,
        "nota_minima": min(valores) if valores else 0,
    }, ensure_ascii=False)
