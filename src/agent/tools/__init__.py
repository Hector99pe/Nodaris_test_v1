"""Tools for Nodaris agent."""

from agent.tools.analizar_abandono import tool_analizar_abandono
from agent.tools.crypto import generate_verification_hash, tool_generar_hash
from agent.tools.detectar_copia import tool_detectar_plagio
from agent.tools.dificultad import tool_evaluar_dificultad
from agent.tools.file_parser import (
    tool_extraer_datos_archivo,
    tool_normalizar_datos_examen,
    tool_solicitar_clarificacion,
)
from agent.tools.tiempos import tool_analizar_tiempos
from agent.tools.validacion import tool_calcular_estadisticas

# All tools available for the agentic loop (bind_tools / ToolNode)
AUDIT_TOOLS = [
    tool_calcular_estadisticas,
    tool_detectar_plagio,
    tool_analizar_abandono,
    tool_analizar_tiempos,
    tool_evaluar_dificultad,
    tool_generar_hash,
    tool_extraer_datos_archivo,
    tool_normalizar_datos_examen,
    tool_solicitar_clarificacion,
]

__all__ = [
    "generate_verification_hash",
    "AUDIT_TOOLS",
    "tool_calcular_estadisticas",
    "tool_detectar_plagio",
    "tool_analizar_abandono",
    "tool_analizar_tiempos",
    "tool_evaluar_dificultad",
    "tool_generar_hash",
    "tool_extraer_datos_archivo",
    "tool_normalizar_datos_examen",
    "tool_solicitar_clarificacion",
]
