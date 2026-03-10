"""State definitions for Nodaris academic audit agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
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

    Attributes:
        dni: Student identification number
        nota: Academic grade (0-20 scale)
        status: Audit status (ok, error)
        mensaje: Error or informational message
        hash: SHA-256 verification hash
        analisis: LLM-generated analysis
        anomalia_detectada: Whether inconsistencies were detected
        usuario_query: User question from Telegram interface
    """

    # Input fields
    dni: str = ""
    nota: int = -1
    usuario_query: str = ""

    # Processing fields
    status: str = ""
    mensaje: str = ""
    hash: str = ""
    analisis: str = ""
    anomalia_detectada: bool = False

    # Legacy compatibility (will be removed)
    changeme: str = "example"
