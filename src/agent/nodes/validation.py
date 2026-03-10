"""Academic data validation node."""

from typing import Dict, Any
from langsmith import traceable

from agent.state import AcademicAuditState
from agent.config import Config


def _normalize_exam_payload(state: AcademicAuditState) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    """Normalize full exam payload to internal exam_data/students_data format.

    Supports both:
    - Already normalized: state.exam_data + state.students_data
    - Full payload in state.exam_data with keys examen/preguntas/estudiantes/resultados
    """
    exam_data = state.exam_data or {}
    students_data = state.students_data or []

    # Already normalized payload
    if "examen" in exam_data and "preguntas" in exam_data and students_data:
        return exam_data, students_data

    # Full payload mode: exam_data contains raw JSON with all sections
    has_full_payload = (
        isinstance(exam_data, dict)
        and "examen" in exam_data
        and "preguntas" in exam_data
        and "estudiantes" in exam_data
        and "resultados" in exam_data
    )
    if not has_full_payload:
        return exam_data, students_data

    estudiantes = exam_data.get("estudiantes", [])
    resultados = exam_data.get("resultados", [])

    estudiantes_by_id = {
        s.get("id", ""): s for s in estudiantes if isinstance(s, dict)
    }

    merged_students: list[Dict[str, Any]] = []
    for resultado in resultados:
        if not isinstance(resultado, dict):
            continue

        estudiante_id = resultado.get("estudiante_id", "")
        base = estudiantes_by_id.get(estudiante_id, {})

        merged_students.append(
            {
                **base,
                "estudiante_id": estudiante_id,
                "respuestas": resultado.get("respuestas", []),
                "tiempo_total": resultado.get("tiempo_total_seg"),
                "tiempo_respuesta": resultado.get("tiempo_pregunta_seg", []),
                "timestamp_inicio": resultado.get("timestamp_inicio"),
                "timestamp_fin": resultado.get("timestamp_fin"),
            }
        )

    normalized_exam_data = {
        "examen": exam_data.get("examen", {}),
        "preguntas": exam_data.get("preguntas", []),
    }
    return normalized_exam_data, merged_students


@traceable(name="validateAcademicData")
async def validate_academic_data(state: AcademicAuditState) -> Dict[str, Any]:
    """Validate academic record inputs.

    Args:
        state: Current workflow state

    Returns:
        Updated state fields with validation results
    """
    exam_data, students_data = _normalize_exam_payload(state)

    # === Full exam mode ===
    if exam_data and (students_data or state.students_data):
        preguntas = exam_data.get("preguntas", []) if isinstance(exam_data, dict) else []
        examen = exam_data.get("examen", {}) if isinstance(exam_data, dict) else {}

        if not isinstance(preguntas, list) or not preguntas:
            return {
                "status": "error",
                "mensaje": "Examen inválido: faltan preguntas",
            }

        if not isinstance(students_data, list) or not students_data:
            return {
                "status": "error",
                "mensaje": "Examen inválido: faltan estudiantes/resultados",
            }

        return {
            "status": "validated",
            "mensaje": f"Datos de examen válidos ({len(students_data)} estudiantes)",
            "exam_data": exam_data,
            "students_data": students_data,
            "usuario_query": state.usuario_query or f"Auditar examen {examen.get('id', 'N/A')}",
        }

    # === Individual mode ===
    dni = state.dni
    nota = state.nota

    # Validate DNI presence
    if not dni or not dni.strip():
        return {
            "status": "error",
            "mensaje": "DNI es requerido",
        }

    # Validate grade range
    if nota < Config.NOTA_MIN or nota > Config.NOTA_MAX:
        return {
            "status": "error",
            "mensaje": f"Nota inválida. Debe estar entre {Config.NOTA_MIN} y {Config.NOTA_MAX}",
        }

    # Validation passed
    return {
        "status": "validated",
        "mensaje": "Datos válidos",
    }
