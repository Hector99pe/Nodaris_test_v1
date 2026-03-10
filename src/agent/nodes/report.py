"""Report generation node for Nodaris agent.

Generates professional audit reports.
"""

from datetime import datetime
from langsmith import traceable
from agent.state import AcademicAuditState


@traceable(name="reportNode")
def report_node(state: AcademicAuditState) -> AcademicAuditState:
    """Generate final audit report.

    Creates a professional, structured report with:
    - Executive summary
    - Detailed findings
    - Statistics
    - Recommendations
    - Verification hash

    Args:
        state: Current workflow state

    Returns:
        Updated state with formatted report
    """
    report_sections = []

    # === HEADER ===
    report_sections.append("=" * 70)
    report_sections.append("📊 REPORTE DE AUDITORÍA ACADÉMICA".center(70))
    report_sections.append("=" * 70)
    report_sections.append("")

    # Timestamp
    if state.timestamp:
        report_sections.append(f"🕐 Fecha: {state.timestamp}")
    else:
        report_sections.append(f"🕐 Fecha: {datetime.now().isoformat()}")

    # Verification hash
    if state.hash:
        report_sections.append(f"🔐 Hash de verificación: {state.hash[:16]}...")

    report_sections.append("")

    # === EXECUTIVE SUMMARY ===
    report_sections.append("─" * 70)
    report_sections.append("📋 RESUMEN EJECUTIVO")
    report_sections.append("─" * 70)
    report_sections.append("")

    # Mode and scope
    if state.exam_data or state.students_data:
        num_students = len(state.students_data)
        report_sections.append("Tipo: Auditoría de examen completo")
        report_sections.append(f"Estudiantes analizados: {num_students}")

        if state.exam_data:
            titulo = state.exam_data.get("titulo", "Sin título")
            report_sections.append(f"Examen: {titulo}")
    else:
        report_sections.append("Tipo: Auditoría individual")
        if state.dni:
            report_sections.append(f"Estudiante: DNI {state.dni}")
            report_sections.append(f"Nota: {state.nota}")

    report_sections.append("")

    # Status
    status_emoji = {
        "ok": "✅",
        "error": "❌",
        "warning": "⚠️",
        "planned": "📝"
    }.get(state.status, "ℹ️")

    report_sections.append(f"Estado: {status_emoji} {state.status.upper()}")
    if state.mensaje:
        report_sections.append(f"Mensaje: {state.mensaje}")

    report_sections.append("")

    # === STATISTICS ===
    if state.promedio > 0 or state.distribucion_notas:
        report_sections.append("─" * 70)
        report_sections.append("📊 ESTADÍSTICAS")
        report_sections.append("─" * 70)
        report_sections.append("")

        if state.promedio > 0:
            report_sections.append(f"Promedio general: {state.promedio:.2f}")

            # Grade interpretation
            if state.promedio >= 17:
                interpretacion = "Excelente"
            elif state.promedio >= 14:
                interpretacion = "Bueno"
            elif state.promedio >= 11:
                interpretacion = "Aprobado"
            else:
                interpretacion = "Desaprobado"
            report_sections.append(f"Clasificación: {interpretacion}")

        if state.preguntas_dificiles > 0:
            report_sections.append(f"Preguntas difíciles: {state.preguntas_dificiles}")

        if state.distribucion_notas:
            report_sections.append("")
            report_sections.append("Distribución de notas:")
            for rango, cantidad in sorted(state.distribucion_notas.items()):
                bar = "█" * (cantidad // 2)  # Visual bar
                report_sections.append(f"  {rango}: {cantidad:3d} {bar}")

        report_sections.append("")

    # === FINDINGS / ANOMALÍAS ===
    findings = []

    # Plagiarism
    if state.copias_detectadas:
        findings.append("🔍 DETECCIÓN DE COPIAS")
        findings.append("")
        findings.append(f"Total de casos sospechosos: {len(state.copias_detectadas)}")

        for i, caso in enumerate(state.copias_detectadas[:5], 1):  # Top 5
            nivel_emoji = "🔴" if caso.get("nivel_sospecha") == "ALTO" else "🟡"
            findings.append(
                f"  {nivel_emoji} Caso {i}: {caso['estudiante1']} ↔ {caso['estudiante2']}"
            )
            findings.append(
                f"     Similitud: {caso['similitud_promedio']:.1%} en {caso['preguntas_similares']} preguntas"
            )

        if len(state.copias_detectadas) > 5:
            findings.append(f"  ... y {len(state.copias_detectadas) - 5} casos más")

        findings.append("")

    # Abandonment
    if state.respuestas_nr:
        findings.append("⚠️ ABANDONO (NR)")
        findings.append("")
        findings.append(f"Estudiantes con respuestas vacías: {len(state.respuestas_nr)}")

        for dni in state.respuestas_nr[:10]:  # Show first 10
            findings.append(f"  • {dni}")

        if len(state.respuestas_nr) > 10:
            findings.append(f"  ... y {len(state.respuestas_nr) - 10} más")

        findings.append("")

    # Suspicious timing
    if state.tiempos_sospechosos:
        findings.append("⏱️ TIEMPOS SOSPECHOSOS")
        findings.append("")
        findings.append(f"Estudiantes con tiempos anómalos: {len(state.tiempos_sospechosos)}")

        for dni in state.tiempos_sospechosos[:10]:
            findings.append(f"  • {dni}")

        findings.append("")

    if findings:
        report_sections.append("─" * 70)
        report_sections.append("🔍 HALLAZGOS PRINCIPALES")
        report_sections.append("─" * 70)
        report_sections.append("")
        report_sections.extend(findings)

    # === ANALYSIS ===
    if state.analisis:
        report_sections.append("─" * 70)
        report_sections.append("🤖 ANÁLISIS DETALLADO")
        report_sections.append("─" * 70)
        report_sections.append("")
        report_sections.append(state.analisis)
        report_sections.append("")

    # === REFLECTION ===
    if state.reflection_notes:
        report_sections.append("─" * 70)
        report_sections.append("🔎 EVALUACIÓN DE CALIDAD")
        report_sections.append("─" * 70)
        report_sections.append("")
        report_sections.append(state.reflection_notes)
        report_sections.append("")

    # === RECOMMENDATIONS ===
    report_sections.append("─" * 70)
    report_sections.append("💡 RECOMENDACIONES")
    report_sections.append("─" * 70)
    report_sections.append("")

    recommendations = []

    # Based on findings
    if state.copias_detectadas:
        if any(c.get("nivel_sospecha") == "ALTO" for c in state.copias_detectadas):
            recommendations.append("• URGENTE: Investigar casos de copia de alto riesgo")
        recommendations.append("• Revisar manualmente las respuestas similares detectadas")
        recommendations.append("• Considerar medidas anti-fraude para futuros exámenes")

    if state.respuestas_nr:
        tasa = (len(state.respuestas_nr) / len(state.students_data)) * 100 if state.students_data else 0
        if tasa > 20:
            recommendations.append("• CRÍTICO: Tasa de abandono alta - Revisar dificultad del examen")
        recommendations.append("• Realizar seguimiento con estudiantes que no respondieron")

    if state.tiempos_sospechosos:
        recommendations.append("• Analizar tiempos de respuesta anómalos")

    if state.preguntas_dificiles > 5:
        recommendations.append("• Considerar el balance de dificultad del examen")

    # Based on confidence
    if state.confidence_score < 0.7:
        recommendations.append("• Revisar manualmente este análisis - confianza media/baja")

    if not recommendations:
        recommendations.append("• No se identificaron acciones inmediatas")
        recommendations.append("• Continuar con monitoreo regular")

    report_sections.extend(recommendations)
    report_sections.append("")

    # === FOOTER ===
    report_sections.append("=" * 70)
    report_sections.append(f"Confianza del análisis: {state.confidence_score:.1%}".center(70))
    report_sections.append("Generado por Nodaris Academic Auditor".center(70))
    report_sections.append("=" * 70)

    # Build final report
    final_report = "\n".join(report_sections)

    # Update state
    state.reporte_final = final_report
    state.status = "completed"
    state.mensaje = "Reporte generado exitosamente"

    return state
