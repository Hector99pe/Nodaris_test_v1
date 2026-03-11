"""Verification hash generation node."""

import hashlib
import json
import logging
from typing import Dict, Any
from langsmith import traceable

from agent.tools.crypto import generate_verification_hash

logger = logging.getLogger("nodaris.verification")


@traceable(name="generateVerification")
async def generate_verification(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate verification hash for academic record.

    Args:
        state: Current workflow state (TypedDict)

    Returns:
        Updated state with verification hash
    """
    # Skip verification if validation failed
    if state.get("status") == "error":
        return {}

    # Generate hash for full exam mode or individual mode
    if state.get("exam_data") or state.get("students_data"):
        payload = {
            "exam_data": state.get("exam_data"),
            "students_data": state.get("students_data"),
        }
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        hash_value = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    else:
        hash_value = generate_verification_hash(
            state.get("dni", ""), state.get("nota", 0)
        )

    logger.info("Verification hash generated: %s...", hash_value[:16])

    return {
        "status": "ok",
        "hash": hash_value,
    }
