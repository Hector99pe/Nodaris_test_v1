"""Tool for analyzing exam time anomalies."""

import json
from typing import Any, Annotated

from langchain_core.tools import tool as langgraph_tool
from langgraph.prebuilt import InjectedState


# === LangGraph Tool Wrapper ===

@langgraph_tool
def tool_analizar_tiempos(
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Analiza tiempos de respuesta sospechosos en el examen.

    Detecta estudiantes que terminaron demasiado rápido (menos del 40% del tiempo esperado).
    Requiere datos de tiempo en los resultados del examen.
    """
    state = state or {}
    students_data = state.get("students_data", [])
    exam_data = state.get("exam_data", {})

    if not students_data or not exam_data:
        return json.dumps({"tipo": "tiempos", "sospechosos": [], "mensaje": "No hay datos de tiempos disponibles"})

    duracion_min = exam_data.get("examen", {}).get("duracion_min", 0)
    if not isinstance(duracion_min, (int, float)) or duracion_min <= 0:
        return json.dumps({"tipo": "tiempos", "sospechosos": [], "mensaje": "Duración del examen no especificada"})

    tiempo_esperado_seg = duracion_min * 60
    sospechosos = []

    for student in students_data:
        dni = str(student.get("dni", ""))
        tiempo_total = student.get("tiempo_total")
        if isinstance(tiempo_total, (int, float)) and tiempo_total > 0:
            porcentaje = (tiempo_total / tiempo_esperado_seg) * 100
            if tiempo_total < (tiempo_esperado_seg * 0.4):
                sospechosos.append({
                    "dni": dni,
                    "tiempo_seg": tiempo_total,
                    "porcentaje_usado": round(porcentaje, 1),
                    "razon": f"Usó solo {porcentaje:.1f}% del tiempo disponible"
                })

    return json.dumps({
        "tipo": "tiempos",
        "sospechosos": [s["dni"] for s in sospechosos],
        "detalle": sospechosos,
        "tiempo_esperado_min": duracion_min,
        "total_analizados": len(students_data),
    }, ensure_ascii=False)
