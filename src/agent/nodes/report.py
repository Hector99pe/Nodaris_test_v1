"""Report generation node for Nodaris agent.

Generates professional audit reports.
"""

from datetime import datetime
from typing import Dict, Any
from langsmith import traceable


@traceable(name="reportNode")
def report_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate final audit report.

    Creates a professional, structured report with:
    - Executive summary
    - Detailed findings
    - Statistics
    - Recommendations
    - Verification hash

    Args:
        state: Current workflow state (TypedDict)

    Returns:
        Dict with reporte_final, status, and mensaje
    """
    report_sections = []

    # === HEADER ===
    report_sections.append("=" * 70)
    report_sections.append("📊 REPORTE DE AUDITORÍA ACADÉMICA".center(70))
    report_sections.append("=" * 70)
    report_sections.append("")

    # Timestamp
    timestamp = state.get("timestamp", "")
    if timestamp:
        report_sections.append(f"🕐 Fecha: {timestamp}")
    else:
        report_sections.append(f"🕐 Fecha: {datetime.now().isoformat()}")

    # Verification hash
    hash_val = state.get("hash", "")
    if hash_val:
        report_sections.append(f"🔐 Hash de verificación: {hash_val[:16]}...")

    report_sections.append("")

    # === EXECUTIVE SUMMARY ===
    report_sections.append("─" * 70)
    report_sections.append("📋 RESUMEN EJECUTIVO")
    report_sections.append("─" * 70)
    report_sections.append("")

    exam_data = state.get("exam_data") or {}
    students_data = state.get("students_data") or []

    if exam_data or students_data:
        num_students = len(students_data)
        report_sections.append("Tipo: Auditoría de examen completo")
        report_sections.append(f"Estudiantes analizados: {num_students}")

        if exam_data:
            examen_info = exam_data.get("examen", {})
            titulo = examen_info.get("curso", exam_data.get("titulo", "Sin título"))
            exam_id = examen_info.get("id", "")
            if exam_id:
                titulo = f"{titulo} ({exam_id})"
            report_sections.append(f"Examen: {titulo}")
    else:
        report_sections.append("Tipo: Auditoría individual")
        dni = state.get("dni", "")
        if dni:
            report_sections.append(f"Estudiante: DNI {dni}")
            report_sections.append(f"Nota: {state.get('nota', 0)}")

    report_sections.append("")

    # Status
    status = state.get("status", "ok")
    status_emoji = {
        "ok": "✅",
        "error": "❌",
        "warning": "⚠️",
        "planned": "📝"
    }.get(status, "ℹ️")

    report_sections.append(f"Estado: {status_emoji} {status.upper()}")
    mensaje = state.get("mensaje", "")
    if mensaje:
        report_sections.append(f"Mensaje: {mensaje}")

    report_sections.append("")

    # === STATISTICS ===
    promedio = state.get("promedio", 0.0)
    distribucion_notas = state.get("distribucion_notas") or {}
    preguntas_dificiles = state.get("preguntas_dificiles", 0)

    if promedio > 0 or distribucion_notas:
        report_sections.append("─" * 70)
        report_sections.append("📊 ESTADÍSTICAS")
        report_sections.append("─" * 70)
        report_sections.append("")

        if promedio > 0:
            report_sections.append(f"Promedio general: {promedio:.2f}")

            if promedio >= 17:
                interpretacion = "Excelente"
            elif promedio >= 14:
                interpretacion = "Bueno"
            elif promedio >= 11:
                interpretacion = "Aprobado"
            else:
                interpretacion = "Desaprobado"
            report_sections.append(f"Clasificación: {interpretacion}")

        if preguntas_dificiles > 0:
            report_sections.append(f"Preguntas difíciles: {preguntas_dificiles}")

        if distribucion_notas:
            report_sections.append("")
            report_sections.append("Distribución de notas:")
            for rango, cantidad in sorted(distribucion_notas.items()):
                bar = "█" * (cantidad // 2)
                report_sections.append(f"  {rango}: {cantidad:3d} {bar}")

        report_sections.append("")

    # === FINDINGS / ANOMALÍAS ===
    findings = []

    copias_detectadas = state.get("copias_detectadas") or []
    respuestas_nr = state.get("respuestas_nr") or []
    tiempos_sospechosos = state.get("tiempos_sospechosos") or []

    if copias_detectadas:
        findings.append("🔍 DETECCIÓN DE COPIAS")
        findings.append("")
        findings.append(f"Total de casos sospechosos: {len(copias_detectadas)}")

        for i, caso in enumerate(copias_detectadas[:5], 1):
            nivel_emoji = "🔴" if caso.get("nivel_sospecha") == "ALTO" else "🟡"
            findings.append(
                f"  {nivel_emoji} Caso {i}: {caso.get('estudiante1', '?')} ↔ {caso.get('estudiante2', '?')}"
            )
            findings.append(
                f"     Similitud: {caso.get('similitud_promedio', 0):.1%} en {caso.get('preguntas_similares', 0)} preguntas"
            )

        if len(copias_detectadas) > 5:
            findings.append(f"  ... y {len(copias_detectadas) - 5} casos más")

        findings.append("")

    if respuestas_nr:
        findings.append("⚠️ ABANDONO (NR)")
        findings.append("")
        findings.append(f"Estudiantes con respuestas vacías: {len(respuestas_nr)}")

        for dni_nr in respuestas_nr[:10]:
            findings.append(f"  • {dni_nr}")

        if len(respuestas_nr) > 10:
            findings.append(f"  ... y {len(respuestas_nr) - 10} más")

        findings.append("")

    if tiempos_sospechosos:
        findings.append("⏱️ TIEMPOS SOSPECHOSOS")
        findings.append("")
        findings.append(f"Estudiantes con tiempos anómalos: {len(tiempos_sospechosos)}")

        for dni_ts in tiempos_sospechosos[:10]:
            findings.append(f"  • {dni_ts}")

        findings.append("")

    if findings:
        report_sections.append("─" * 70)
        report_sections.append("🔍 HALLAZGOS PRINCIPALES")
        report_sections.append("─" * 70)
        report_sections.append("")
        report_sections.extend(findings)

    # === ANALYSIS ===
    analisis = state.get("analisis", "")
    if analisis:
        report_sections.append("─" * 70)
        report_sections.append("🤖 ANÁLISIS DETALLADO")
        report_sections.append("─" * 70)
        report_sections.append("")
        report_sections.append(analisis)
        report_sections.append("")

    # === REFLECTION ===
    reflection_notes = state.get("reflection_notes", "")
    if reflection_notes:
        report_sections.append("─" * 70)
        report_sections.append("🔎 EVALUACIÓN DE CALIDAD")
        report_sections.append("─" * 70)
        report_sections.append("")
        report_sections.append(reflection_notes)
        report_sections.append("")

    # === RECOMMENDATIONS ===
    report_sections.append("─" * 70)
    report_sections.append("💡 RECOMENDACIONES")
    report_sections.append("─" * 70)
    report_sections.append("")

    recommendations = []

    if copias_detectadas:
        if any(c.get("nivel_sospecha") == "ALTO" for c in copias_detectadas):
            recommendations.append("• URGENTE: Investigar casos de copia de alto riesgo")
        recommendations.append("• Revisar manualmente las respuestas similares detectadas")
        recommendations.append("• Considerar medidas anti-fraude para futuros exámenes")

    if respuestas_nr:
        tasa = (len(respuestas_nr) / len(students_data)) * 100 if students_data else 0
        if tasa > 20:
            recommendations.append("• CRÍTICO: Tasa de abandono alta - Revisar dificultad del examen")
        recommendations.append("• Realizar seguimiento con estudiantes que no respondieron")

    if tiempos_sospechosos:
        recommendations.append("• Analizar tiempos de respuesta anómalos")

    if preguntas_dificiles > 5:
        recommendations.append("• Considerar el balance de dificultad del examen")

    confidence_score = state.get("confidence_score", 0.0)
    if confidence_score < 0.7:
        recommendations.append("• Revisar manualmente este análisis - confianza media/baja")

    if not recommendations:
        recommendations.append("• No se identificaron acciones inmediatas")
        recommendations.append("• Continuar con monitoreo regular")

    report_sections.extend(recommendations)
    report_sections.append("")

    # === FOOTER ===
    report_sections.append("=" * 70)
    report_sections.append(f"Confianza del análisis: {confidence_score:.1%}".center(70))
    report_sections.append("Generado por Nodaris Academic Auditor".center(70))
    report_sections.append("=" * 70)

    final_report = "\n".join(report_sections)

    return {
        "reporte_final": final_report,
        "status": "completed",
        "mensaje": "Reporte generado exitosamente",
    }
