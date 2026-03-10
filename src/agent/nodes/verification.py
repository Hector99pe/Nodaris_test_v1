"""Verification hash generation node."""

import hashlib
import json
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

    # Generate hash for full exam mode or individual mode
    if state.exam_data or state.students_data:
        payload = {
            "exam_data": state.exam_data,
            "students_data": state.students_data,
            "analysis_to_run": state.analysis_to_run,
        }
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        hash_value = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    else:
        hash_value = generate_verification_hash(state.dni, state.nota)

    return {
        "status": "ok",
        "hash": hash_value,
    }
