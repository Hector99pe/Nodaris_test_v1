"""Tool for managing exam time limits.

Tracks and validates exam duration and time constraints.
"""

from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class TiempoExamen:
    """Exam time configuration."""

    duracion_minutos: int
    tiempo_adicional: int = 0

    @property
    def duracion_total(self) -> int:
        """Calculate total exam duration including additional time."""
        return self.duracion_minutos + self.tiempo_adicional


def calcular_tiempo_restante(
    hora_inicio: datetime,
    duracion_minutos: int
) -> Dict[str, Any]:
    """Calculate remaining time for an exam.

    Args:
        hora_inicio: Exam start time
        duracion_minutos: Exam duration in minutes

    Returns:
        Dictionary with time remaining information
    """
    ahora = datetime.now()
    hora_fin = hora_inicio + timedelta(minutes=duracion_minutos)
    tiempo_transcurrido = (ahora - hora_inicio).total_seconds() / 60
    tiempo_restante = duracion_minutos - tiempo_transcurrido

    return {
        "tiempo_transcurrido_min": round(tiempo_transcurrido, 2),
        "tiempo_restante_min": round(max(0, tiempo_restante), 2),
        "hora_fin_prevista": hora_fin.isoformat(),
        "tiempo_agotado": tiempo_restante <= 0
    }


def validar_tiempo_examen(
    duracion_minutos: int,
    tipo_examen: str = "regular"
) -> Dict[str, Any]:
    """Validate if exam duration is appropriate.

    Args:
        duracion_minutos: Proposed exam duration
        tipo_examen: Type of exam (regular, parcial, final)

    Returns:
        Dictionary with validation results
    """
    # Standard time limits by exam type
    limites = {
        "regular": (30, 120),
        "parcial": (60, 180),
        "final": (90, 240)
    }

    min_time, max_time = limites.get(tipo_examen, (30, 120))

    es_valido = min_time <= duracion_minutos <= max_time

    return {
        "valido": es_valido,
        "duracion_propuesta": duracion_minutos,
        "rango_recomendado": f"{min_time}-{max_time} minutos",
        "tipo_examen": tipo_examen,
        "mensaje": "Duración válida" if es_valido else f"Duración fuera del rango recomendado ({min_time}-{max_time} min)"
    }


def estimar_tiempo_por_pregunta(
    num_preguntas: int,
    duracion_total: int
) -> float:
    """Estimate time available per question.

    Args:
        num_preguntas: Number of questions
        duracion_total: Total exam duration in minutes

    Returns:
        Average time per question in minutes
    """
    if num_preguntas == 0:
        return 0.0

    return round(duracion_total / num_preguntas, 2)
