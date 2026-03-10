"""Tool for detecting plagiarism in exam responses.

Analyzes answer similarity to identify potential cheating.
"""

import json
from typing import List, Dict, Any, Annotated
from difflib import SequenceMatcher

from langchain_core.tools import tool as langgraph_tool
from langgraph.prebuilt import InjectedState


def calcular_similitud(texto1: str, texto2: str) -> float:
    """Calculate similarity between two texts.

    Args:
        texto1: First text
        texto2: Second text

    Returns:
        Similarity score between 0 and 1
    """
    if not texto1 or not texto2:
        return 0.0

    # Normalize texts
    t1 = texto1.lower().strip()
    t2 = texto2.lower().strip()

    # Calculate similarity
    similarity = SequenceMatcher(None, t1, t2).ratio()
    return round(similarity, 3)


def detectar_copia(
    respuestas_estudiantes: List[Dict[str, Any]],
    umbral_similitud: float = 0.85
) -> List[Dict[str, Any]]:
    """Detect potential plagiarism between student responses.

    Args:
        respuestas_estudiantes: List of student responses with structure:
            [{"dni": "...", "respuestas": ["answer1", "answer2", ...]}, ...]
        umbral_similitud: Similarity threshold (0-1) to flag as potential copy

    Returns:
        List of detected plagiarism cases with similarity scores
    """
    copias_detectadas = []
    n_estudiantes = len(respuestas_estudiantes)

    # Compare each pair of students
    for i in range(n_estudiantes):
        for j in range(i + 1, n_estudiantes):
            estudiante1 = respuestas_estudiantes[i]
            estudiante2 = respuestas_estudiantes[j]

            dni1 = estudiante1.get("dni", f"Estudiante_{i}")
            dni2 = estudiante2.get("dni", f"Estudiante_{j}")

            respuestas1 = estudiante1.get("respuestas", [])
            respuestas2 = estudiante2.get("respuestas", [])

            # Compare each question's answer
            similitudes = []
            for idx, (r1, r2) in enumerate(zip(respuestas1, respuestas2)):
                if isinstance(r1, str) and isinstance(r2, str):
                    similitud = calcular_similitud(r1, r2)
                    if similitud >= umbral_similitud:
                        similitudes.append({
                            "pregunta": idx + 1,
                            "similitud": similitud,
                            "respuesta1": r1[:100],  # First 100 chars
                            "respuesta2": r2[:100]
                        })

            # If multiple high-similarity answers, flag as potential copy
            if len(similitudes) >= 2:  # At least 2 similar answers
                promedio_similitud = sum(s["similitud"] for s in similitudes) / len(similitudes)

                copias_detectadas.append({
                    "estudiante1": dni1,
                    "estudiante2": dni2,
                    "preguntas_similares": len(similitudes),
                    "similitud_promedio": round(promedio_similitud, 3),
                    "detalles": similitudes,
                    "nivel_sospecha": "ALTO" if promedio_similitud > 0.95 else "MEDIO"
                })

    # Sort by similarity (highest first)
    copias_detectadas.sort(key=lambda x: x["similitud_promedio"], reverse=True)

    return copias_detectadas


def analizar_patrones_copia(
    copias_detectadas: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Analyze patterns in detected plagiarism cases.

    Args:
        copias_detectadas: List of detected plagiarism cases

    Returns:
        Dictionary with pattern analysis
    """
    if not copias_detectadas:
        return {
            "total_casos": 0,
            "nivel_general": "NINGUNO",
            "estudiantes_involucrados": []
        }

    # Count involved students
    estudiantes = set()
    for caso in copias_detectadas:
        estudiantes.add(caso["estudiante1"])
        estudiantes.add(caso["estudiante2"])

    # Count severity levels
    casos_alto = sum(1 for c in copias_detectadas if c["nivel_sospecha"] == "ALTO")
    casos_medio = len(copias_detectadas) - casos_alto

    # Determine overall level
    if casos_alto > 0:
        nivel_general = "CRÍTICO"
    elif casos_medio >= 3:
        nivel_general = "ALTO"
    elif casos_medio > 0:
        nivel_general = "MEDIO"
    else:
        nivel_general = "BAJO"

    return {
        "total_casos": len(copias_detectadas),
        "casos_alto_riesgo": casos_alto,
        "casos_medio_riesgo": casos_medio,
        "estudiantes_involucrados": list(estudiantes),
        "nivel_general": nivel_general,
        "requiere_investigacion": nivel_general in ["CRÍTICO", "ALTO"]
    }


# === LangGraph Tool Wrapper ===

@langgraph_tool
def tool_detectar_plagio(
    umbral: float = 0.85,
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Detecta plagio entre estudiantes comparando sus respuestas del examen.

    Compara las respuestas de cada par de estudiantes y calcula similitud.
    Usar cuando hay 2 o más estudiantes en el examen.

    Args:
        umbral: Umbral de similitud (0-1) para considerar copia. Default 0.85
    """
    students_data = (state or {}).get("students_data", [])
    if len(students_data) < 2:
        return json.dumps({"tipo": "plagio", "copias_detectadas": [], "mensaje": "Se necesitan al menos 2 estudiantes"})

    copias = detectar_copia(students_data, umbral)
    patrones = analizar_patrones_copia(copias)

    return json.dumps({
        "tipo": "plagio",
        "copias_detectadas": copias,
        "patrones": patrones,
        "total_casos": len(copias),
    }, ensure_ascii=False)
