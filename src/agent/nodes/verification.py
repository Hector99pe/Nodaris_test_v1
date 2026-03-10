"""Verification hash generation node."""

from typing import Dict, Any
from langsmith import traceable

from agent.state import AcademicAuditState
from agent.tools.crypto import generate_verification_hash


@traceable(name="generateVerification")
async def generate_verification(state: AcademicAuditState) -> Dict[str, Any]:
    """Generate verification hash for academic record.

    Args:
        state: Current workflow state

    Returns:
        Updated state with verification hash
    """
    # Skip verification if validation failed
    if state.status == "error":
        return {}

    # Generate hash
    hash_value = generate_verification_hash(state.dni, state.nota)

    return {
        "status": "ok",
        "hash": hash_value,
    }
