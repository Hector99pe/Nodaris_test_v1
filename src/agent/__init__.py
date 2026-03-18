"""Nodaris Academic Audit Agent.

LangGraph-based agent for auditing academic records with OpenAI analysis.

Mission:
    Auditar resultados académicos y generar registros verificables.

Components:
    - graph: Main LangGraph workflow
    - state: State definitions
    - nodes: Processing nodes (validation, analysis, verification)
    - tools: Utilities (crypto, prompts)
    - config: Configuration management
"""

from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE importing Config (which reads env vars at import time)
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
load_dotenv(_env_path)

from agent.config import Config  # noqa: E402
from agent.graph import graph  # noqa: E402
from agent.state import AcademicAuditState  # noqa: E402

__all__ = ["graph", "AcademicAuditState", "Config"]
