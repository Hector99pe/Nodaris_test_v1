"""State definitions for Nodaris academic audit agent."""

from __future__ import annotations

from typing import Any, Annotated, List, Dict
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


class AcademicAuditState(TypedDict, total=False):
    """State for academic audit workflow.

    Supports two modes:
    1. Individual student audit (dni + nota)
    2. Full exam audit (exam_data with multiple students)
    3. File-based audit (Excel/PDF/JSON)

    Uses TypedDict with add_messages reducer for agentic loop.
    All fields are optional (total=False) so nodes only return what they update.
    """

    # === CORE: Agentic conversation ===
    messages: Annotated[list, add_messages]

    # === INPUT: Individual mode ===
    dni: str
    nota: int

    # === INPUT: Exam mode ===
    exam_data: Dict[str, Any]
    students_data: List[Dict[str, Any]]

    # === INPUT: File mode ===
    file_path: str
    file_type: str

    # === INPUT: Query ===
    usuario_query: str

    # === PLANNING ===
    plan: str

    # === PROCESSING ===
    status: str
    mensaje: str

    # === ANALYSIS RESULTS ===
    analisis: str
    anomalia_detectada: bool

    # Specific detections
    copias_detectadas: List[Dict[str, Any]]
    tiempos_sospechosos: List[str]
    tiempos_detalle: List[Dict[str, Any]]
    respuestas_nr: List[str]
    abandono_detalle: List[Dict[str, Any]]

    # Statistics
    promedio: float
    preguntas_dificiles: int
    distribucion_notas: Dict[str, int]

    # === VERIFICATION ===
    hash: str
    timestamp: str

    # === REFLECTION ===
    reflection_notes: str
    confidence_score: float
    iteration_count: int

    # === REPORT ===
    reporte_final: str

    # === LEARNING MEMORY ===
    learning_hint: str
    learned_tools: List[str]
