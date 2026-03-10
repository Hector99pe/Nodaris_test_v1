"""Prompt templates for LLM interactions."""

from typing import List, Dict
from langsmith import traceable


@traceable(name="buildAuditPrompt")
def build_audit_prompt(dni: str, nota: int) -> List[Dict[str, str]]:
    """Build messages for academic audit analysis.

    Args:
        dni: Student identification number
        nota: Academic grade

    Returns:
        List of message dictionaries for LLM
    """
    system_prompt = """Eres un auditor académico experto.

Tu misión:
- Analizar resultados académicos
- Detectar posibles inconsistencias
- Generar recomendaciones

Escala de notas: 0-20
- 0-10: Desaprobado
- 11-13: Aprobado
- 14-16: Bueno
- 17-18: Muy bueno
- 19-20: Excelente

Responde de forma concisa y profesional."""

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
