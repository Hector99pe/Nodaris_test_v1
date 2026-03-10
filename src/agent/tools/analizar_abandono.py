"""Tool for analyzing student abandonment (NR - No Response).

Identifies and analyzes students who didn't complete the exam.
"""

from typing import List, Dict, Any


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
        respuestas = estudiante.get("respuestas", [])

        if not respuestas:
            estudiantes_nr.append({
                "dni": dni,
                "tipo": "ABANDONO_TOTAL",
                "respuestas_vacias": len(respuestas),
                "porcentaje_vacio": 100.0,
                "nota_esperada": 0
            })
            continue

        # Count empty or very short responses
        vacias = 0
        for respuesta in respuestas:
            if isinstance(respuesta, str):
                if not respuesta.strip() or respuesta.strip().upper() in ["NR", "N/R", "NO RESPONDIÓ"]:
                    vacias += 1
                elif len(respuesta.strip()) < 5:  # Very short answer
                    vacias += 0.5

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


def correlacionar_abandono_dificultad(
    estudiantes_nr: List[Dict[str, Any]],
    preguntas_dificiles: List[int]
) -> Dict[str, Any]:
    """Correlate abandonment with difficult questions.

    Args:
        estudiantes_nr: Students with NR status
        preguntas_dificiles: Indices of difficult questions

    Returns:
        Correlation analysis
    """
    if not estudiantes_nr or not preguntas_dificiles:
        return {"correlacion": False, "mensaje": "Datos insuficientes para correlación"}

    # This is a simplified correlation
    # In a real implementation, you'd analyze which specific questions were left unanswered

    return {
        "correlacion": True,
        "mensaje": f"Se detectaron {len(estudiantes_nr)} abandonos en un examen con {len(preguntas_dificiles)} preguntas difíciles",
        "hipotesis": "La dificultad del examen puede estar relacionada con la tasa de abandono",
        "recomendacion": "Considerar ajustar la dificultad o el tiempo del examen"
    }
