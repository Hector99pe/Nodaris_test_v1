"""Report generation node for Nodaris agent.

Generates professional audit reports with output guardrails.
"""

import logging
import unicodedata
from datetime import datetime
from typing import Dict, Any
from langsmith import traceable

from agent.storage import AuditStore

logger = logging.getLogger("nodaris.report")

_BOX_W = 45    # inner display-width for section boxes
_FRAME_W = 70  # inner display-width for main frame


def _dw(text: str) -> int:
    """Display width of *text*, counting wide/emoji chars as 2 columns."""
    w = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def _pad(text: str, width: int) -> str:
    """Right-pad *text* to *width* display columns."""
    return text + " " * max(width - _dw(text), 0)


def _section(emoji: str, title: str) -> list[str]:
    """Build a 3-line section header box with correct alignment."""
    inner = f"  {emoji}  {title}"
    return [
        "┌" + "─" * _BOX_W + "┐",
        "│" + _pad(inner, _BOX_W) + "│",
        "└" + "─" * _BOX_W + "┘",
    ]


def _frame(ch: str = "═", left: str = "╔", right: str = "╗") -> str:
    """Build a horizontal frame line."""
    return left + ch * _FRAME_W + right


def _frame_text(text: str) -> str:
    """Build a ║ … ║ line with display-width-aware padding."""
    return "║" + _pad(text, _FRAME_W) + "║"


def _evaluate_report_quality(report_text: str, confidence_score: float) -> str | None:
    """Use LLM to evaluate report quality and coherence.

    Returns a brief quality assessment string, or None if evaluation fails.
    Only runs for reports with enough substance (audit, not conversational).
    """
    from agent.config import Config

    if not Config.OPENAI_API_KEY or len(report_text) < 200:
        return None

    try:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr
        from agent.resilience import call_with_llm_circuit_breaker

        llm = ChatOpenAI(
            api_key=SecretStr(Config.OPENAI_API_KEY),
            model=Config.OPENAI_MODEL,
            temperature=0.1,
        )

        prompt = f"""Evalúa la calidad de este reporte de auditoría académica en máximo 3 líneas.
Verifica:
1. ¿Los hallazgos son coherentes con las estadísticas mostradas?
2. ¿Las recomendaciones son relevantes a los hallazgos?
3. ¿Falta algún análisis importante?

Confianza del análisis: {confidence_score:.1%}

Reporte:
{report_text[:3000]}

Responde en formato: "Calidad: [ALTA/MEDIA/BAJA]. [Breve justificación]"."""

        response = call_with_llm_circuit_breaker(
            lambda: llm.invoke(prompt)
        )
        evaluation = response.content.strip() if response.content else None
        if evaluation:
            logger.info("Report quality evaluation: %s", evaluation[:80])
        return evaluation
    except Exception as e:
        logger.warning("Report quality evaluation failed: %s", e)
        return None


def _validate_report_guardrails(state: Dict[str, Any], report_text: str) -> str:
    """Output guardrail: remove report sections that reference non-existent data.

    Prevents the report from presenting fabricated findings by checking
    whether the state actually contains the data backing each section.
    Returns a cleaned report with a warning appended if sections were removed.
    """
    copias = state.get("copias_detectadas") or []
    respuestas_nr = state.get("respuestas_nr") or []
    tiempos = state.get("tiempos_sospechosos") or []

    # Map: section keyword → (state data that must exist, label)
    phantom_checks = [
        ("DETECCIÓN DE COPIAS", copias, "Detección de copias"),
        ("ABANDONO", respuestas_nr, "Abandono/NR"),
        ("TIEMPOS SOSPECHOSOS", tiempos, "Tiempos sospechosos"),
    ]

    lines = report_text.split("\n")
    cleaned: list[str] = []
    removed_sections: list[str] = []
    skipping = False

    def _is_section_boundary(text: str) -> bool:
        """Detect section boundary: ─ dividers or ┌── box headers."""
        stripped = text.strip()
        if not stripped:
            return False
        if len(stripped) >= 10 and all(c in ("─", "=") for c in stripped):
            return True
        if stripped.startswith("┌") and "─" in stripped:
            return True
        return False

    for line in lines:
        stripped = line.strip()

        # Check if this is a known section header with no backing data
        matched_phantom = False
        if not skipping:
            for keyword, data, label in phantom_checks:
                if keyword in stripped and not data:
                    skipping = True
                    matched_phantom = True
                    removed_sections.append(f"{label} (sin datos)")
                    break

        if matched_phantom:
            continue

        if skipping:
            # Stop skipping when we reach a section boundary (next section)
            if _is_section_boundary(stripped):
                skipping = False
                cleaned.append(line)  # Keep boundary — belongs to next section
            # Either way, skip/continue
            continue

        cleaned.append(line)

    if removed_sections:
        logger.warning("Guardrail removed %d phantom sections: %s", len(removed_sections), removed_sections)

    return "\n".join(cleaned)


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
    lines: list[str] = []

    # ── Metadata ──
    timestamp = state.get("timestamp") or datetime.now().isoformat()
    hash_val = state.get("hash", "")
    confidence_score = state.get("confidence_score", 0.0)

    # ── Determine audit type info ──
    exam_data = state.get("exam_data") or {}
    students_data = state.get("students_data") or []
    is_individual = not exam_data and not students_data and state.get("dni")

    # ================================================================
    # HEADER
    # ================================================================
    title = "📊  REPORTE DE AUDITORÍA ACADÉMICA  📊"
    left_pad = (_FRAME_W - _dw(title)) // 2
    lines.append(_frame())
    lines.append(_frame_text(" " * left_pad + title))
    lines.append(_frame("═", "╚", "╝"))
    lines.append("")

    # ── Meta row ──
    meta_parts = [f"📅 {timestamp[:16].replace('T', ' ')}"]
    if hash_val:
        meta_parts.append(f"🔐 {hash_val[:16]}…")
    meta_parts.append(f"📈 Confianza: {confidence_score:.0%}")
    lines.append("  │  ".join(meta_parts))
    lines.append("")

    # ================================================================
    # RESUMEN EJECUTIVO
    # ================================================================
    lines.extend(_section("📋", "RESUMEN EJECUTIVO"))
    lines.append("")

    if is_individual:
        dni = state.get("dni", "")
        nota = state.get("nota", 0)
        lines.append("  • Tipo: Auditoría individual")
        lines.append(f"  • Estudiante: DNI {dni}")
        lines.append(f"  • Nota: {nota}/20")
    else:
        num_students = len(students_data)
        lines.append("  • Tipo: Auditoría de examen completo")
        lines.append(f"  • Estudiantes: {num_students}")
        if exam_data:
            examen_info = exam_data.get("examen", {})
            curso = examen_info.get("curso", exam_data.get("titulo", "Sin título"))
            exam_id = examen_info.get("id", "")
            label = f"{curso} ({exam_id})" if exam_id else curso
            lines.append(f"  • Examen: {label}")
            preguntas = exam_data.get("preguntas", [])
            if preguntas:
                lines.append(f"  • Preguntas: {len(preguntas)}")

    # Status
    status = state.get("status", "ok")
    status_map = {"ok": "✅ OK", "error": "❌ ERROR", "warning": "⚠️ ALERTA", "planned": "📝 PLANIFICADO"}
    lines.append(f"  • Estado: {status_map.get(status, 'ℹ️ ' + status.upper())}")

    anomalia = state.get("anomalia_detectada", False)
    if anomalia:
        lines.append("")
        lines.append("  ⚠️  SE DETECTARON ANOMALÍAS — Ver hallazgos abajo")

    lines.append("")

    # ================================================================
    # ESTADÍSTICAS
    # ================================================================
    promedio = state.get("promedio", 0.0)
    distribucion_notas = state.get("distribucion_notas") or {}
    preguntas_dificiles = state.get("preguntas_dificiles", 0)

    if promedio > 0 or distribucion_notas:
        lines.extend(_section("📊", "ESTADÍSTICAS"))
        lines.append("")

        if promedio > 0:
            if promedio >= 17:
                nivel, barra = "Excelente", "🟢"
            elif promedio >= 14:
                nivel, barra = "Bueno", "🔵"
            elif promedio >= 11:
                nivel, barra = "Aprobado", "🟡"
            else:
                nivel, barra = "Desaprobado", "🔴"
            lines.append(f"  • Promedio general: {promedio:.2f}/20  {barra} {nivel}")

        if preguntas_dificiles > 0:
            lines.append(f"  • Preguntas difíciles: {preguntas_dificiles}")

        if distribucion_notas:
            lines.append("")
            lines.append("  Distribución de notas:")
            total = sum(distribucion_notas.values()) or 1
            for rango, cantidad in sorted(distribucion_notas.items()):
                pct = (cantidad / total) * 100
                bar_len = int(pct / 5)
                bar = "▓" * bar_len + "░" * (20 - bar_len)
                lines.append(f"    {rango:>5}  │ {bar} {cantidad} ({pct:.0f}%)")

        lines.append("")

    # ================================================================
    # HALLAZGOS PRINCIPALES
    # ================================================================
    copias_detectadas = state.get("copias_detectadas") or []
    respuestas_nr = state.get("respuestas_nr") or []
    tiempos_sospechosos = state.get("tiempos_sospechosos") or []

    has_findings = copias_detectadas or respuestas_nr or tiempos_sospechosos

    if has_findings:
        lines.extend(_section("🔍", "HALLAZGOS PRINCIPALES"))
        lines.append("")

    if copias_detectadas:
        lines.append(f"  🔍 DETECCIÓN DE COPIAS  ({len(copias_detectadas)} caso{'s' if len(copias_detectadas) != 1 else ''})")
        lines.append("  " + "─" * 40)
        for i, caso in enumerate(copias_detectadas[:5], 1):
            nivel = caso.get("nivel_sospecha", "MEDIO")
            icon = "🔴" if nivel == "ALTO" else "🟡"
            e1 = caso.get("estudiante1", "?")
            e2 = caso.get("estudiante2", "?")
            sim = caso.get("similitud_promedio", 0)
            pregs = caso.get("preguntas_similares", 0)
            lines.append(f"    {icon} {i}. {e1} ↔ {e2}")
            lines.append(f"       Similitud: {sim:.0%}  •  Preguntas coincidentes: {pregs}  •  Riesgo: {nivel}")
        if len(copias_detectadas) > 5:
            lines.append(f"    … y {len(copias_detectadas) - 5} caso(s) adicional(es)")
        lines.append("")

    if respuestas_nr:
        lines.append(f"  ⚠️ ABANDONO (NR)  ({len(respuestas_nr)} estudiante{'s' if len(respuestas_nr) != 1 else ''})")
        lines.append("  " + "─" * 40)
        if students_data:
            tasa = (len(respuestas_nr) / len(students_data)) * 100
            lines.append(f"    Tasa de abandono: {tasa:.1f}%")
        for item in respuestas_nr[:8]:
            display = str(item).strip() if item else "(sin identificar)"
            lines.append(f"    • {display}")
        if len(respuestas_nr) > 8:
            lines.append(f"    … y {len(respuestas_nr) - 8} más")
        lines.append("")

    if tiempos_sospechosos:
        lines.append(f"  ⏱️ TIEMPOS SOSPECHOSOS  ({len(tiempos_sospechosos)} estudiante{'s' if len(tiempos_sospechosos) != 1 else ''})")
        lines.append("  " + "─" * 40)
        for item in tiempos_sospechosos[:8]:
            display = str(item).strip() if item else "(sin identificar)"
            lines.append(f"    • {display}")
        if len(tiempos_sospechosos) > 8:
            lines.append(f"    … y {len(tiempos_sospechosos) - 8} más")
        lines.append("")

    # ================================================================
    # ANÁLISIS DETALLADO (from agent_reasoner)
    # ================================================================
    analisis = state.get("analisis", "")
    if analisis:
        lines.extend(_section("🤖", "ANÁLISIS DETALLADO"))
        lines.append("")
        lines.append(analisis)
        lines.append("")

    # ================================================================
    # EVALUACIÓN DE CALIDAD (reflection)
    # ================================================================
    reflection_notes = state.get("reflection_notes", "")
    if reflection_notes:
        lines.extend(_section("🔎", "EVALUACIÓN DE CALIDAD"))
        lines.append("")
        for _rl in reflection_notes.split("\n"):
            lines.append(f"  {_rl}" if _rl.strip() else "")
        lines.append("")

    # ================================================================
    # RECOMENDACIONES
    # ================================================================
    lines.extend(_section("💡", "RECOMENDACIONES"))
    lines.append("")

    recommendations = []

    if copias_detectadas:
        if any(c.get("nivel_sospecha") == "ALTO" for c in copias_detectadas):
            recommendations.append("🔴 URGENTE: Investigar casos de copia de alto riesgo")
        recommendations.append("   Revisar manualmente las respuestas similares detectadas")
        recommendations.append("   Considerar medidas anti-fraude para futuros exámenes")

    if respuestas_nr:
        tasa = (len(respuestas_nr) / len(students_data)) * 100 if students_data else 0
        if tasa > 20:
            recommendations.append("🔴 CRÍTICO: Tasa de abandono alta — revisar dificultad del examen")
        recommendations.append("   Realizar seguimiento con estudiantes que no respondieron")

    if tiempos_sospechosos:
        recommendations.append("🟡 Analizar tiempos de respuesta anómalos en detalle")

    if preguntas_dificiles > 5:
        recommendations.append("🟡 Considerar el balance de dificultad del examen")

    if confidence_score < 0.7:
        recommendations.append("🟡 Revisar manualmente este análisis — confianza media/baja")

    if not recommendations:
        recommendations.append("🟢 No se identificaron acciones inmediatas")
        recommendations.append("   Continuar con monitoreo regular")

    for rec in recommendations:
        lines.append(f"  {rec}")
    lines.append("")

    # ================================================================
    # FOOTER
    # ================================================================
    lines.append(_frame())
    lines.append(_frame_text(f"  📈 Confianza: {confidence_score:.0%}  │  Nodaris Academic Auditor"))
    lines.append(_frame("═", "╚", "╝"))

    final_report = "\n".join(lines)

    # === OUTPUT GUARDRAIL: remove sections referencing non-existent data ===
    final_report = _validate_report_guardrails(state, final_report)

    # === QUALITY EVALUATION: LLM validates report coherence ===
    quality_eval = _evaluate_report_quality(final_report, confidence_score)
    if quality_eval:
        final_report += f"\n\n🔎 Evaluación de calidad: {quality_eval}"

    audit_id = None
    try:
        audit_id = AuditStore().save_audit(state, final_report)
    except Exception:
        # Report generation must not fail if persistence is temporarily unavailable.
        audit_id = None

    mensaje = "Reporte generado exitosamente"
    if audit_id is not None:
        mensaje = f"Reporte generado y persistido (audit_id={audit_id})"

    return {
        "reporte_final": final_report,
        "status": "completed",
        "mensaje": mensaje,
    }
