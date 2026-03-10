"""LLM analysis node for academic auditing."""

from typing import Dict, Any
from langsmith import traceable

from agent.state import AcademicAuditState
from agent.tools.prompts import build_audit_prompt
from agent.tools.detectar_copia import detectar_copia
from agent.tools.analizar_abandono import identificar_nr


@traceable(run_type="llm", name="invokeLLM")
async def _invoke_llm(messages: list) -> Dict[str, str]:
    """Invoke LLM for analysis.

    Args:
        messages: Formatted prompt messages

    Returns:
        LLM response with content
    """
    from openai import AsyncOpenAI
    from agent.config import Config

    if not Config.OPENAI_API_KEY:
        return {"content": "Error: OPENAI_API_KEY no configurada"}

    client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)

    try:
        response = await client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=messages,
            temperature=Config.OPENAI_TEMPERATURE
        )
        return {"content": response.choices[0].message.content or ""}
    except Exception as e:
        return {"content": f"Error al invocar LLM: {str(e)}"}


@traceable(name="analyzeWithLLM")
async def analyze_with_llm(state: AcademicAuditState) -> Dict[str, Any]:
    """Analyze academic record using LLM.

    Args:
        state: Current workflow state

    Returns:
        Updated state with analysis results
    """
    # Skip analysis if validation failed
    if state.status == "error":
        return {}

    exam_mode = bool(state.exam_data and state.students_data)

    promedio = 0.0
    distribucion_notas: Dict[str, int] = {}
    copias_detectadas = []
    respuestas_nr = []
    tiempos_sospechosos = []

    # Enrich analysis with full exam information when available
    if exam_mode:
        preguntas = state.exam_data.get("preguntas", []) if state.exam_data else []
        correctas = [str(p.get("correcta", "")).upper() for p in preguntas if isinstance(p, dict)]

        notas: list[float] = []
        for student in state.students_data:
            respuestas = student.get("respuestas", [])
            if not correctas or not isinstance(respuestas, list):
                continue

            aciertos = 0
            for idx, respuesta in enumerate(respuestas[: len(correctas)]):
                if str(respuesta).upper() == correctas[idx]:
                    aciertos += 1

            nota_20 = (aciertos / len(correctas)) * 20 if correctas else 0
            notas.append(nota_20)

        if notas:
            promedio = round(sum(notas) / len(notas), 2)

            buckets = {
                "0-10": 0,
                "11-13": 0,
                "14-16": 0,
                "17-20": 0,
            }
            for nota in notas:
                if nota <= 10:
                    buckets["0-10"] += 1
                elif nota <= 13:
                    buckets["11-13"] += 1
                elif nota <= 16:
                    buckets["14-16"] += 1
                else:
                    buckets["17-20"] += 1
            distribucion_notas = buckets

        if "detectar_copia" in state.analysis_to_run:
            copias_detectadas = detectar_copia(state.students_data)

        if "analizar_abandono" in state.analysis_to_run:
            abandono = identificar_nr(state.students_data)
            respuestas_nr = [str(item.get("dni", "")) for item in abandono if item.get("dni")]

        if "analizar_tiempos" in state.analysis_to_run:
            for student in state.students_data:
                dni = str(student.get("dni", ""))
                tiempo_total = student.get("tiempo_total")
                if isinstance(tiempo_total, (int, float)) and tiempo_total > 0:
                    # Heuristica simple: menos de 40% del tiempo esperado del examen.
                    duracion_min = state.exam_data.get("examen", {}).get("duracion_min", 0)
                    if isinstance(duracion_min, (int, float)) and duracion_min > 0:
                        tiempo_esperado_seg = duracion_min * 60
                        if tiempo_total < (tiempo_esperado_seg * 0.4):
                            tiempos_sospechosos.append(dni)

        exam_id = state.exam_data.get("examen", {}).get("id", "N/A") if state.exam_data else "N/A"
        messages = [
            {
                "role": "system",
                "content": "Eres un auditor académico experto. Resume hallazgos de forma profesional y accionable.",
            },
            {
                "role": "user",
                "content": (
                    f"Analiza este examen completo y entrega hallazgos claros.\n"
                    f"Examen: {exam_id}\n"
                    f"Estudiantes: {len(state.students_data)}\n"
                    f"Promedio (0-20): {promedio}\n"
                    f"Distribución: {distribucion_notas}\n"
                    f"Posibles copias: {len(copias_detectadas)}\n"
                    f"Abandono (NR): {len(respuestas_nr)}\n"
                    f"Tiempos sospechosos: {len(tiempos_sospechosos)}\n"
                    "Incluye: resumen ejecutivo, riesgos y recomendaciones puntuales."
                ),
            },
        ]
    else:
        # Individual mode prompt
        messages = build_audit_prompt(state.dni, state.nota)

    # Build prompt and invoke LLM
    response = await _invoke_llm(messages)

    # Parse response for anomaly detection (look for actual alerts in LLM response)
    content = response.get("content", "")
    anomalia_keywords = ["⚠", "alerta:", "anomalía detectada", "sospechoso", "inconsistencia"]
    anomalia_detectada = any(keyword in content.lower() for keyword in anomalia_keywords)

    return {
        "analisis": content,
        "anomalia_detectada": anomalia_detectada,
        "promedio": promedio,
        "distribucion_notas": distribucion_notas,
        "copias_detectadas": copias_detectadas,
        "respuestas_nr": respuestas_nr,
        "tiempos_sospechosos": tiempos_sospechosos,
    }
