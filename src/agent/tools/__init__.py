"""Tools and utilities for Nodaris agent."""

# Legacy tools
from agent.tools.crypto import generate_verification_hash
from agent.tools.prompts import build_audit_prompt

# New tools
from agent.tools.dificultad import evaluar_dificultad, analizar_distribucion_dificultad
from agent.tools.copia import copiar_examen, respaldar_datos
from agent.tools.tiempos import (
    calcular_tiempo_restante,
    validar_tiempo_examen,
    estimar_tiempo_por_pregunta,
    TiempoExamen
)
from agent.tools.validacion import (
    validar_dni,
    validar_nota,
    validar_estructura_examen,
    validar_respuestas
)
from agent.tools.detectar_copia import (
    detectar_copia,
    calcular_similitud,
    analizar_patrones_copia
)
from agent.tools.analizar_abandono import (
    identificar_nr,
    analizar_abandono,
    correlacionar_abandono_dificultad
)

__all__ = [
    # Legacy
    "generate_verification_hash",
    "build_audit_prompt",
    # Difficulty
    "evaluar_dificultad",
    "analizar_distribucion_dificultad",
    # Copy
    "copiar_examen",
    "respaldar_datos",
    # Time
    "calcular_tiempo_restante",
    "validar_tiempo_examen",
    "estimar_tiempo_por_pregunta",
    "TiempoExamen",
    # Validation
    "validar_dni",
    "validar_nota",
    "validar_estructura_examen",
    "validar_respuestas",
    # Plagiarism detection
    "detectar_copia",
    "calcular_similitud",
    "analizar_patrones_copia",
    # Abandonment analysis
    "identificar_nr",
    "analizar_abandono",
    "correlacionar_abandono_dificultad",
]
