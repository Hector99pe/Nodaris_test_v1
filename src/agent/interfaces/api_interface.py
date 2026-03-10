"""API interface for Nodaris agent.

Provides REST API endpoints for the agent.
"""

from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# TODO: Implement FastAPI interface
# This will provide HTTP endpoints for the agent


class AuditRequest(BaseModel):
    """Request model for audit endpoint."""

    dni: str
    nota: int


class AuditResponse(BaseModel):
    """Response model for audit endpoint."""

    status: str
    mensaje: str
    analisis: str
    hash: str


app = FastAPI(title="Nodaris Agent API")


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/audit", response_model=AuditResponse)
async def audit_academic_data(request: AuditRequest) -> AuditResponse:
    """Audit academic data endpoint.

    Args:
        request: Audit request with DNI and nota

    Returns:
        Audit response with analysis and verification
    """
    # TODO: Integrate with LangGraph workflow
    raise HTTPException(status_code=501, detail="Not implemented yet")
