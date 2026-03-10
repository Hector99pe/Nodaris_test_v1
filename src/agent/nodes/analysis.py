"""LLM analysis node for academic auditing."""

from typing import Dict, Any
from langsmith import traceable

from agent.state import AcademicAuditState
from agent.tools.prompts import build_audit_prompt


@traceable(run_type="llm", name="invokeLLM")
async def _invoke_llm(messages: list) -> Dict[str, str]:
    """Invoke LLM for analysis.

    TODO: Replace with actual OpenAI API call when ready.
    Current: Placeholder implementation for testing.

    Args:
        messages: Formatted prompt messages

    Returns:
        LLM response with content
    """
    # Placeholder - will be replaced with:
    # from openai import AsyncOpenAI
    # client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
    # response = await client.chat.completions.create(
    #     model=Config.OPENAI_MODEL,
    #     messages=messages,
    #     temperature=Config.OPENAI_TEMPERATURE
    # )
    # return {"content": response.choices[0].message.content}

    user_content = messages[-1]["content"]
    return {
        "content": f"Análisis académico generado para: {user_content}"
    }


@traceable(name="analyzeWithLLM")
async def analyze_with_llm(state: AcademicAuditState) -> Dict[str, Any]:
    """Analyze academic record using LLM.

    Args:
        state: Current workflow state

    Returns:
        Updated state with analysis results
    """
    # Skip analysis if validation failed
    if state.status == "error":
        return {}

    # Build prompt and invoke LLM
    messages = build_audit_prompt(state.dni, state.nota)
    response = await _invoke_llm(messages)

    # Parse response for anomaly detection (look for actual alerts in LLM response)
    content = response.get("content", "")
    anomalia_keywords = ["⚠", "alerta:", "anomalía detectada", "sospechoso", "inconsistencia"]
    anomalia_detectada = any(keyword in content.lower() for keyword in anomalia_keywords)

    return {
        "analisis": content,
        "anomalia_detectada": anomalia_detectada,
    }
