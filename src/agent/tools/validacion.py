"""Tool for validating academic data.

Provides validation utilities for exams, grades, and student data.
"""

import re
from typing import Dict, List, Optional, Tuple, Any


def validar_dni(dni: str) -> Tuple[bool, str]:
    """Validate Peruvian DNI format.

    Args:
        dni: DNI string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not dni:
        return False, "DNI no puede estar vacío"

    # Remove whitespace
    dni = dni.strip()

    # Check if it's 8 digits
    if not re.match(r'^\d{8}$', dni):
        return False, "DNI debe tener exactamente 8 dígitos"

    return True, ""


def validar_nota(nota: int, escala_min: int = 0, escala_max: int = 20) -> Tuple[bool, str]:
    """Validate academic grade.

    Args:
        nota: Grade to validate
        escala_min: Minimum valid grade
        escala_max: Maximum valid grade

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(nota, (int, float)):
        return False, "La nota debe ser un número"

    if nota < escala_min or nota > escala_max:
        return False, f"La nota debe estar entre {escala_min} y {escala_max}"

    return True, ""


def validar_estructura_examen(examen: Dict) -> Dict[str, Any]:
    """Validate exam data structure.

    Args:
        examen: Exam dictionary to validate

    Returns:
        Dictionary with validation results
    """
    errores = []
    advertencias = []

    # Required fields
    campos_requeridos = ["titulo", "preguntas", "duracion"]
    for campo in campos_requeridos:
        if campo not in examen:
            errores.append(f"Campo requerido faltante: {campo}")

    # Validate questions
    if "preguntas" in examen:
        preguntas = examen["preguntas"]
        if not isinstance(preguntas, list):
            errores.append("'preguntas' debe ser una lista")
        elif len(preguntas) == 0:
            advertencias.append("El examen no tiene preguntas")
        else:
            for i, pregunta in enumerate(preguntas):
                if not isinstance(pregunta, dict):
                    errores.append(f"Pregunta {i+1} tiene formato inválido")
                elif "texto" not in pregunta:
                    errores.append(f"Pregunta {i+1} no tiene texto")

    # Validate duration
    if "duracion" in examen:
        duracion = examen["duracion"]
        if not isinstance(duracion, (int, float)) or duracion <= 0:
            errores.append("La duración debe ser un número positivo")

    return {
        "valido": len(errores) == 0,
        "errores": errores,
        "advertencias": advertencias
    }


def validar_respuestas(
    respuestas: List[Dict],
    preguntas: List[Dict]
) -> Dict[str, Any]:
    """Validate student answers against questions.

    Args:
        respuestas: List of student answers
        preguntas: List of exam questions

    Returns:
        Dictionary with validation results
    """
    if len(respuestas) != len(preguntas):
        return {
            "valido": False,
            "mensaje": f"Número de respuestas ({len(respuestas)}) no coincide con preguntas ({len(preguntas)})"
        }

    respuestas_validas = 0
    respuestas_vacias = 0

    for i, (respuesta, pregunta) in enumerate(zip(respuestas, preguntas)):
        if not respuesta.get("texto"):
            respuestas_vacias += 1
        else:
            respuestas_validas += 1

    return {
        "valido": True,
        "total_preguntas": len(preguntas),
        "respuestas_validas": respuestas_validas,
        "respuestas_vacias": respuestas_vacias,
        "porcentaje_completado": round(respuestas_validas / len(preguntas) * 100, 2)
    }
