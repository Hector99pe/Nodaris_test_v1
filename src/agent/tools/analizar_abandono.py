"""Tool for analyzing student abandonment (NR - No Response).

Identifies and analyzes students who didn't complete the exam.
"""

import json
from typing import Annotated, Any, Dict, List

from langchain_core.tools import tool as langgraph_tool
from langgraph.prebuilt import InjectedState


def identificar_nr(
    respuestas_estudiantes: List[Dict[str, Any]],
    umbral_vacias: float = 0.5
) -> List[Dict[str, Any]]:
    """Identify students with NR (No Response) status.

    Args:
        respuestas_estudiantes: List of student responses
        umbral_vacias: Threshold of empty answers to consider NR (0-1)

    Returns:
        List of students with NR status and analysis
    """
    estudiantes_nr = []

    for estudiante in respuestas_estudiantes:
        dni = estudiante.get("dni", "")

        # If the student record has no "respuestas" key at all, the source
        # data simply doesn't contain response columns — skip silently
        # instead of marking as abandonment.
        if "respuestas" not in estudiante:
            continue

        respuestas = estudiante["respuestas"]

        if not respuestas:
            estudiantes_nr.append({
                "dni": dni,
                "tipo": "ABANDONO_TOTAL",
                "respuestas_vacias": 0,
                "porcentaje_vacio": 100.0,
                "nota_esperada": 0
            })
            continue

        # Count empty / NR responses
        vacias = 0
        _NR_VALUES = {"", "NR", "N/R", "NO RESPONDIÓ", "-", "_", "*"}
        for respuesta in respuestas:
            if isinstance(respuesta, str):
                cleaned = respuesta.strip().upper()
                if not cleaned or cleaned in _NR_VALUES:
                    vacias += 1

        porcentaje_vacio = (vacias / len(respuestas)) * 100

        # Classify if above threshold
        if porcentaje_vacio >= (umbral_vacias * 100):
            tipo = "ABANDONO_TOTAL" if porcentaje_vacio >= 80 else "ABANDONO_PARCIAL"

            estudiantes_nr.append({
                "dni": dni,
                "tipo": tipo,
                "respuestas_vacias": int(vacias),
                "total_preguntas": len(respuestas),
                "porcentaje_vacio": round(porcentaje_vacio, 1),
                "nota_esperada": 0 if tipo == "ABANDONO_TOTAL" else "BAJA"
            })

    return estudiantes_nr


def analizar_abandono(
    estudiantes_nr: List[Dict[str, Any]],
    total_estudiantes: int
) -> Dict[str, Any]:
    """Analyze abandonment patterns.

    Args:
        estudiantes_nr: List of students with NR status
        total_estudiantes: Total number of students

    Returns:
        Dictionary with abandonment analysis
    """
    if not estudiantes_nr:
        return {
            "tasa_abandono": 0.0,
            "nivel": "NINGUNO",
            "total_nr": 0,
            "recomendaciones": ["No se detectó abandono en el examen"]
        }

    # Calculate statistics
    abandono_total = sum(1 for e in estudiantes_nr if e["tipo"] == "ABANDONO_TOTAL")
    abandono_parcial = len(estudiantes_nr) - abandono_total

    tasa_abandono = (len(estudiantes_nr) / total_estudiantes) * 100 if total_estudiantes > 0 else 0

    # Determine severity level
    if tasa_abandono >= 30:
        nivel = "CRÍTICO"
        recomendaciones = [
            "Revisar si hubo problemas técnicos durante el examen",
            "Verificar si las instrucciones fueron claras",
            "Considerar la dificultad del examen"
        ]
    elif tasa_abandono >= 15:
        nivel = "ALTO"
        recomendaciones = [
            "Investigar causas del abandono",
            "Revisar tiempo asignado al examen"
        ]
    elif tasa_abandono >= 5:
        nivel = "MEDIO"
        recomendaciones = [
            "Monitorear estudiantes que abandonaron",
            "Considerar seguimiento individual"
        ]
    else:
        nivel = "BAJO"
        recomendaciones = [
            "Tasa de abandono dentro de lo normal"
        ]

    return {
        "total_nr": len(estudiantes_nr),
        "abandono_total": abandono_total,
        "abandono_parcial": abandono_parcial,
        "tasa_abandono": round(tasa_abandono, 2),
        "nivel": nivel,
        "recomendaciones": recomendaciones,
        "estudiantes_criticos": [e["dni"] for e in estudiantes_nr if e["tipo"] == "ABANDONO_TOTAL"]
    }


# === LangGraph Tool Wrapper ===

@langgraph_tool
def tool_analizar_abandono(
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Analiza el abandono de estudiantes en el examen.

    Identifica estudiantes que no respondieron (NR) y calcula tasas de abandono.
    Clasifica severidad: CRÍTICO (>=30%), ALTO (>=15%), MEDIO (>=5%), BAJO (<5%).
    """
    students_data = (state or {}).get("students_data", [])
    if not students_data:
        return json.dumps({"tipo": "abandono", "estudiantes_nr": [], "mensaje": "No hay datos de estudiantes"})

    # Check if response data exists at all
    has_responses = any("respuestas" in s for s in students_data)

    estudiantes_nr = identificar_nr(students_data)
    analisis = analizar_abandono(estudiantes_nr, len(students_data))

    # Build display labels and enrich detail dicts with nombre/apellido
    student_labels = []
    students_by_dni = {s.get("dni", ""): s for s in students_data if s.get("dni")}
    for e in estudiantes_nr:
        dni = e.get("dni", "")
        base = students_by_dni.get(dni, {})
        nombre = base.get("nombre", "")
        e["nombre"] = nombre
        e["apellido"] = base.get("apellido", "")
        pct = e.get("porcentaje_vacio", 0)
        label = f"{dni} — {nombre}" if nombre else (dni or "Desconocido")
        label += f" ({pct:.0f}% vacío)" if pct < 100 else " (no respondió)"
        student_labels.append(label)

    result: Dict[str, Any] = {
        "tipo": "abandono",
        "estudiantes_nr": student_labels,
        "detalle_abandono": estudiantes_nr,
        "analisis": analisis,
    }

    if not has_responses:
        result["observacion"] = (
            "No se encontraron columnas de respuestas en los datos. "
            "No es posible determinar abandono sin datos de respuestas. "
            "Los datos solo contienen identificación y/o notas."
        )
        result["estudiantes_nr"] = []
        result["detalle_abandono"] = []

    return json.dumps(result, ensure_ascii=False)
