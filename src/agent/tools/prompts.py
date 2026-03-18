"""Prompt templates for LLM interactions."""

from pathlib import Path
from typing import Dict, List

from langsmith import traceable

_SOUL_PATH = Path(__file__).resolve().parents[3] / "SOUL.md"
_INSTINCT_PATH = Path(__file__).resolve().parents[3] / "instinct.md"


def load_soul() -> str:
    """Load SOUL.md content used as the agent identity/system prompt."""
    content = _SOUL_PATH.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError("SOUL.md esta vacio. Define la identidad del agente.")
    return content


def load_instinct() -> str:
    """Load instinct.md content used for default autonomous behaviour."""
    content = _INSTINCT_PATH.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError("instinct.md esta vacio. Define el comportamiento base del agente.")
    return content


def build_agent_system_prompt(context: str) -> str:
    """Build full system prompt from SOUL, instinct, and runtime context."""
    soul = load_soul()
    instinct = load_instinct()
    context_text = context.strip() if isinstance(context, str) else ""
    if not context_text:
        context_text = "No hay contexto adicional."
    return (
        f"{soul}\n\n"
        f"Instintos operativos (instinct.md):\n{instinct}\n\n"
        f"Contexto actual:\n{context_text}"
    )


@traceable(name="buildAuditPrompt")
def build_audit_prompt(dni: str, nota: int) -> List[Dict[str, str]]:
    """Build messages for academic audit analysis.

    Args:
        dni: Student identification number
        nota: Academic grade

    Returns:
        List of message dictionaries for LLM
    """
    system_prompt = build_agent_system_prompt("")

    user_prompt = f"""Analiza el siguiente registro:
- DNI: {dni}
- Nota: {nota}

Proporciona:
1. Clasificación del resultado
2. Observaciones (si las hay)
3. Alertas de anomalía (si detectas patrones inusuales)"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
