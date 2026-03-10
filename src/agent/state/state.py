"""State definitions for Nodaris academic audit agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from typing_extensions import TypedDict


class Context(TypedDict):
    """Runtime configuration context.

    Configurable parameters passed at assistant creation or invocation.
    """

    openai_model: str  # e.g., "gpt-4", "gpt-3.5-turbo"
    temperature: float  # LLM temperature for analysis


@dataclass
class AcademicAuditState:
    """State for academic audit workflow.

    Supports two modes:
    1. Individual student audit (dni + nota)
    2. Full exam audit (exam_data with multiple students)

    Attributes:
        # Individual mode
        dni: Student identification number
        nota: Academic grade (0-20 scale)

        # Exam mode
        exam_data: Complete exam data with questions and answers
        students_data: List of student responses

        # Query
        usuario_query: User question from interface

        # Planning
        plan: Execution plan from planner node
        analysis_to_run: List of analysis types to execute

        # Processing results
        status: Audit status (ok, error, warning)
        mensaje: Status message

        # Analysis results
        analisis: Main LLM-generated analysis
        anomalia_detectada: Whether inconsistencies were detected

        # Specific detections
        copias_detectadas: List of potential plagiarism cases
        tiempos_sospechosos: Students with suspicious timing
        respuestas_nr: Students who didn't respond (NR)

        # Statistics
        promedio: Average grade
        preguntas_dificiles: Count of difficult questions
        distribucion_notas: Grade distribution

        # Verification
        hash: SHA-256 verification hash
        timestamp: Audit timestamp

        # Reflection
        reflection_notes: Insights from reflection node
        confidence_score: Confidence in audit results (0-1)

        # Report
        reporte_final: Final formatted report
    """

    # === INPUT FIELDS ===
    # Individual mode
    dni: str = ""
    nota: int = -1

    # Exam mode
    exam_data: Optional[Dict[str, Any]] = None
    students_data: List[Dict[str, Any]] = field(default_factory=list)

    # Query
    usuario_query: str = ""

    # === PLANNING ===
    plan: str = ""
    analysis_to_run: List[str] = field(default_factory=list)

    # === PROCESSING ===
    status: str = ""
    mensaje: str = ""

    # === ANALYSIS RESULTS ===
    analisis: str = ""
    anomalia_detectada: bool = False

    # Specific detections
    copias_detectadas: List[Dict[str, Any]] = field(default_factory=list)
    tiempos_sospechosos: List[str] = field(default_factory=list)
    respuestas_nr: List[str] = field(default_factory=list)

    # Statistics
    promedio: float = 0.0
    preguntas_dificiles: int = 0
    distribucion_notas: Dict[str, int] = field(default_factory=dict)

    # === VERIFICATION ===
    hash: str = ""
    timestamp: str = ""

    # === REFLECTION ===
    reflection_notes: str = ""
    confidence_score: float = 0.0

    # === REPORT ===
    reporte_final: str = ""
