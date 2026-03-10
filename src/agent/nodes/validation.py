"""Academic data validation node."""

from typing import Dict, Any
from langsmith import traceable

from agent.state import AcademicAuditState
from agent.config import Config


@traceable(name="validateAcademicData")
async def validate_academic_data(state: AcademicAuditState) -> Dict[str, Any]:
    """Validate academic record inputs.

    Args:
        state: Current workflow state

    Returns:
        Updated state fields with validation results
    """
    dni = state.dni
    nota = state.nota

    # Validate DNI presence
    if not dni or not dni.strip():
        return {
            "status": "error",
            "mensaje": "DNI es requerido",
        }

    # Validate grade range
    if nota < Config.NOTA_MIN or nota > Config.NOTA_MAX:
        return {
            "status": "error",
            "mensaje": f"Nota inválida. Debe estar entre {Config.NOTA_MIN} y {Config.NOTA_MAX}",
        }

    # Validation passed
    return {
        "status": "validated",
        "mensaje": "Datos válidos",
    }
