"""Reflection node for Nodaris agent.

Reviews analysis results for quality assurance.
Can trigger re-planning if confidence is too low.
"""

import json
import logging
from typing import Dict, Any

from langchain_core.messages import HumanMessage, ToolMessage
from langsmith import traceable

from agent.config import Config
from agent.storage import AuditStore

logger = logging.getLogger("nodaris.reflection")


def _extract_tool_results(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured data from tool messages in state."""
    updates: Dict[str, Any] = {}
    messages = state.get("messages", [])

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            continue

        tipo = data.get("tipo")
        if tipo == "estadisticas":
            updates["promedio"] = data.get("promedio", 0.0)
            updates["distribucion_notas"] = data.get("distribucion", {})
        elif tipo == "plagio":
            updates["copias_detectadas"] = data.get("copias_detectadas", [])
        elif tipo == "abandono":
            updates["respuestas_nr"] = data.get("estudiantes_nr", [])
        elif tipo == "tiempos":
            updates["tiempos_sospechosos"] = data.get("sospechosos", [])
        elif tipo == "dificultad":
            updates["preguntas_dificiles"] = data.get("preguntas_dificiles", 0)
        elif tipo == "archivo":
            # File extraction tool returned data - inject into state
            datos = data.get("datos")
            if isinstance(datos, dict) and "examen" in datos and "preguntas" in datos:
                if "estudiantes" in datos and "resultados" in datos:
                    from agent.nodes.validation import _normalize_exam_payload
                    exam_d, students_d = _normalize_exam_payload({"exam_data": datos})
                    updates["exam_data"] = exam_d
                    updates["students_data"] = students_d
        elif tipo == "normalizacion":
            # Normalization tool returned student data
            students = data.get("students_data", [])
            if students:
                updates["students_data"] = students
            datos = data.get("datos")
            if isinstance(datos, dict) and "examen" in datos:
                from agent.nodes.validation import _normalize_exam_payload
                exam_d, students_d = _normalize_exam_payload({"exam_data": datos})
                updates["exam_data"] = exam_d
                if students_d:
                    updates["students_data"] = students_d

    updates["anomalia_detectada"] = bool(
        updates.get("copias_detectadas")
        or updates.get("tiempos_sospechosos")
        or updates.get("respuestas_nr")
    )

    return updates


def _infer_tool_names(messages: list[Any]) -> list[str]:
    """Infer high-level tool categories from tool message payloads."""
    names: list[str] = []
    mapping = {
        "estadisticas": "calcular_estadisticas",
        "plagio": "detectar_plagio",
        "abandono": "analizar_abandono",
        "tiempos": "analizar_tiempos",
        "dificultad": "evaluar_dificultad",
        "archivo": "extraer_datos_archivo",
        "normalizacion": "normalizar_datos_examen",
    }

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError):
            continue
        tipo = data.get("tipo")
        tool_name = mapping.get(tipo)
        if tool_name and tool_name not in names:
            names.append(tool_name)
    return names


def _infer_mode(state: Dict[str, Any]) -> str:
    if state.get("file_path"):
        return "file"
    if state.get("exam_data") or state.get("students_data"):
        return "full_exam"
    if state.get("dni"):
        return "individual"
    return "conversational"


@traceable(name="reflectionNode")
def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reflect on analysis results, extract structured data, and score confidence.

    Responsibilities:
    1. Extract structured data from tool messages into state fields
    2. Evaluate quality and consistency of the analysis
    3. Calculate confidence score
    4. If confidence is too low, inject feedback for re-planning

    Args:
        state: Current workflow state

    Returns:
        Updated state with extracted data, reflection notes, and confidence score
    """
    # === Conversational mode - no audit data, skip deep reflection ===
    if (
        not state.get("exam_data")
        and not state.get("students_data")
        and not state.get("file_path")
        and not state.get("dni")
    ):
        return {
            "reflection_notes": "Modo conversacional - sin datos para auditar",
            "confidence_score": 1.0,
        }

    # === Step 1: Extract structured data from tool messages ===
    extracted = _extract_tool_results(state)

    # === Step 2: Quality evaluation ===
    reflection_notes = []
    issues_found = []
    confidence_factors = []

    messages = state.get("messages", [])
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    num_tools_used = len(tool_messages)

    # Check if we actually have data to analyze
    has_actual_data = bool(
        state.get("students_data")
        or extracted.get("students_data")
        or state.get("exam_data")
        or extracted.get("exam_data")
        or state.get("dni")
    )

    if num_tools_used == 0:
        reflection_notes.append("\u26a0\ufe0f No se ejecutaron herramientas de an\u00e1lisis")
        confidence_factors.append(0.3)
    elif not has_actual_data:
        # Tools ran but no real data was extracted — file parsing likely failed
        reflection_notes.append(f"\u26a0\ufe0f Se ejecutaron {num_tools_used} herramientas pero no se obtuvieron datos")
        reflection_notes.append("\u26a0\ufe0f No se pudo extraer informaci\u00f3n del archivo para analizar")
        confidence_factors.append(0.2)
        issues_found.append("No se pudieron extraer datos del archivo")
    else:
        reflection_notes.append(f"✓ Se ejecutaron {num_tools_used} herramientas de análisis")
        confidence_factors.append(0.8)

    # Check plagiarism results
    copias = extracted.get("copias_detectadas", [])
    if copias:
        num_copias = len(copias)
        reflection_notes.append(f"✓ Detectadas {num_copias} posibles copias")
        copias_alto = sum(1 for c in copias if c.get("nivel_sospecha") == "ALTO")
        if copias_alto > 0:
            confidence_factors.append(0.9)
            reflection_notes.append(f"  - {copias_alto} casos de alto riesgo con evidencia fuerte")
        else:
            confidence_factors.append(0.6)
            reflection_notes.append("  ⚠️ Copias detectadas pero evidencia limitada")
            issues_found.append("Verificar manualmente las copias detectadas")

    # Check abandonment
    respuestas_nr = extracted.get("respuestas_nr", [])
    if respuestas_nr:
        num_nr = len(respuestas_nr)
        reflection_notes.append(f"✓ Identificados {num_nr} estudiantes con abandono")
        confidence_factors.append(0.85)

        students_data = state.get("students_data", [])
        if students_data:
            tasa = (num_nr / len(students_data)) * 100
            if tasa > 30:
                issues_found.append(f"⚠️ Tasa de abandono alta ({tasa:.1f}%) - Investigar causas")

    # Check timing
    sospechosos = extracted.get("tiempos_sospechosos", [])
    if sospechosos:
        reflection_notes.append(f"✓ Detectados {len(sospechosos)} tiempos sospechosos")
        confidence_factors.append(0.85)

    # Check statistics
    promedio = extracted.get("promedio", 0.0)
    if promedio > 0:
        reflection_notes.append(f"✓ Promedio calculado: {promedio}")
        confidence_factors.append(0.95)

    # Check anomaly consistency
    if extracted.get("anomalia_detectada"):
        reflection_notes.append("✓ Anomalías detectadas con evidencia de soporte")
        confidence_factors.append(0.9)

    # === Step 3: Calculate confidence ===
    if confidence_factors:
        confidence_score = sum(confidence_factors) / len(confidence_factors)
    else:
        confidence_score = 0.5

    logger.info("Reflection: tools_used=%d, confidence=%.3f, has_data=%s", num_tools_used, confidence_score, has_actual_data)

    if issues_found:
        reflection_notes.append("\n🔍 Requiere atención:")
        reflection_notes.extend(f"  - {issue}" for issue in issues_found)
        confidence_score *= 0.9

    # Quality label
    if confidence_score >= 0.9:
        quality = "EXCELENTE"
    elif confidence_score >= 0.75:
        quality = "BUENA"
    elif confidence_score >= 0.6:
        quality = "ACEPTABLE"
    else:
        quality = "REQUIERE REVISIÓN"

    reflection_notes.append(f"\n📊 Calidad del análisis: {quality}")
    reflection_notes.append(f"📈 Nivel de confianza: {confidence_score:.2%}")

    # === Step 4: Feedback for re-planning if needed ===
    feedback_messages = []
    iteration = state.get("iteration_count", 0)
    max_iterations = 3

    if confidence_score < 0.7 and iteration < max_iterations:
        missing = []
        students_data = state.get("students_data", [])

        if not promedio and students_data:
            missing.append("calcular estadísticas (tool_calcular_estadisticas)")
        if len(students_data) >= 2 and not copias and not any(
            "plagio" in getattr(m, "content", "") for m in tool_messages
        ):
            missing.append("detectar plagio (tool_detectar_plagio)")

        feedback = (
            f"REFLECTION FEEDBACK: Confianza {confidence_score:.2f} (insuficiente). "
            f"Iteración {iteration}/{max_iterations}. "
        )
        if missing:
            feedback += f"Análisis faltantes: {', '.join(missing)}. "
        if issues_found:
            feedback += f"Problemas: {'; '.join(issues_found)}. "
        feedback += "Profundiza usando las herramientas disponibles."

        feedback_messages.append(HumanMessage(content=feedback))

    # Build result
    result: Dict[str, Any] = {
        "reflection_notes": "\n".join(reflection_notes),
        "confidence_score": round(confidence_score, 3),
    }

    # Merge extracted data
    result.update(extracted)

    if feedback_messages:
        result["messages"] = feedback_messages

    # === Step 5: Persist learning memory for adaptive planning ===
    if Config.LEARNING_MEMORY_ENABLED:
        try:
            tool_names = _infer_tool_names(messages)
            if tool_names:
                AuditStore().record_learning_batch(
                    mode=_infer_mode(state),
                    tool_names=tool_names,
                    confidence_score=float(result["confidence_score"]),
                    anomaly_detected=bool(extracted.get("anomalia_detectada")),
                )
        except Exception:
            # Reflection must not fail due to memory persistence issues.
            pass

    return result
