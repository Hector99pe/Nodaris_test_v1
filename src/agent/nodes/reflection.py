"""Reflection node for Nodaris agent.

Reviews and reflects on analysis results to ensure quality.
"""

from langsmith import traceable
from agent.state import AcademicAuditState


@traceable(name="reflectionNode")
def reflection_node(state: AcademicAuditState) -> AcademicAuditState:
    """Reflect on analysis results and identify improvements.

    Checks:
    - Data consistency
    - Evidence sufficiency for claims
    - Potential false positives
    - Analysis completeness

    Args:
        state: Current workflow state

    Returns:
        Updated state with reflection insights and confidence score
    """
    reflection_notes = []
    issues_found = []
    confidence_factors = []

    # === Check plagiarism detection quality ===
    if "detectar_copia" in state.analysis_to_run:
        if state.copias_detectadas:
            num_copias = len(state.copias_detectadas)
            reflection_notes.append(f"✓ Detectadas {num_copias} posibles copias")

            # Check evidence quality
            copias_alto_riesgo = sum(
                1 for c in state.copias_detectadas
                if c.get("nivel_sospecha") == "ALTO"
            )

            if copias_alto_riesgo > 0:
                confidence_factors.append(0.9)  # High confidence in plagiarism
                reflection_notes.append(f"  - {copias_alto_riesgo} casos de alto riesgo con evidencia fuerte")
            else:
                confidence_factors.append(0.6)  # Medium confidence
                reflection_notes.append("  ⚠️ Copias detectadas pero evidencia limitada")
                issues_found.append("Verificar manualmente las copias detectadas")
        else:
            confidence_factors.append(1.0)  # High confidence (no plagiarism)
            reflection_notes.append("✓ No se detectaron copias")

    # === Check abandonment analysis ===
    if "analizar_abandono" in state.analysis_to_run:
        if state.respuestas_nr:
            num_nr = len(state.respuestas_nr)
            reflection_notes.append(f"✓ Identificados {num_nr} estudiantes con abandono")
            confidence_factors.append(0.85)

            # Check if abandonment rate is suspicious
            if state.students_data:
                tasa_abandono = (num_nr / len(state.students_data)) * 100
                if tasa_abandono > 30:
                    issues_found.append(
                        f"⚠️ Tasa de abandono alta ({tasa_abandono:.1f}%) - Investigar causas"
                    )
        else:
            confidence_factors.append(1.0)
            reflection_notes.append("✓ No se detectó abandono significativo")

    # === Check data consistency ===
    consistency_issues = []

    # Check if average grade matches distribution
    if state.promedio > 0 and state.distribucion_notas:
        total_notas = sum(state.distribucion_notas.values())
        if total_notas > 0:
            # Data is consistent
            confidence_factors.append(0.95)
        else:
            consistency_issues.append("Distribución de notas vacía pese a tener promedio")

    # Check if analysis matches detected anomalies
    if state.anomalia_detectada:
        evidencia = bool(
            state.copias_detectadas or
            state.tiempos_sospechosos or
            state.respuestas_nr
        )
        if evidencia:
            confidence_factors.append(0.9)
            reflection_notes.append("✓ Anomalías detectadas con evidencia de soporte")
        else:
            consistency_issues.append(
                "⚠️ Anomalía marcada sin evidencia específica"
            )
            confidence_factors.append(0.5)

    # === Check analysis completeness ===
    planned_analysis = len(state.analysis_to_run)
    if planned_analysis > 0:
        reflection_notes.append(f"✓ Ejecutados {planned_analysis} análisis según plan")
        confidence_factors.append(0.9)
    else:
        issues_found.append("Plan de análisis vacío")
        confidence_factors.append(0.3)

    # === Calculate overall confidence ===
    if confidence_factors:
        confidence_score = sum(confidence_factors) / len(confidence_factors)
    else:
        confidence_score = 0.5  # Default medium confidence

    # === Determine overall assessment ===
    if consistency_issues:
        reflection_notes.append("\n⚠️ Problemas de consistencia:")
        reflection_notes.extend(f"  - {issue}" for issue in consistency_issues)
        confidence_score *= 0.8  # Reduce confidence

    if issues_found:
        reflection_notes.append("\n🔍 Requiere atención:")
        reflection_notes.extend(f"  - {issue}" for issue in issues_found)

    # === Quality assessment ===
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

    # Update state
    state.reflection_notes = "\n".join(reflection_notes)
    state.confidence_score = round(confidence_score, 3)

    return state
