"""Conversational agent for Telegram chat interface."""

from __future__ import annotations

import json
from typing import Dict, Any, List, Optional
from langsmith import traceable

from agent.config import Config
from agent.state import AcademicAuditState
from agent.graph import graph


# Tool definitions for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "auditar_registro",
            "description": "Audita un registro académico verificando DNI y nota, detecta anomalías y genera un hash de verificación",
            "parameters": {
                "type": "object",
                "properties": {
                    "dni": {
                        "type": "string",
                        "description": "DNI del estudiante (8 dígitos)"
                    },
                    "nota": {
                        "type": "integer",
                        "description": "Nota académica en escala 0-20"
                    }
                },
                "required": ["dni", "nota"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verificar_hash",
            "description": "Verifica la autenticidad de un registro académico usando su hash SHA-256",
            "parameters": {
                "type": "object",
                "properties": {
                    "dni": {
                        "type": "string",
                        "description": "DNI del estudiante"
                    },
                    "nota": {
                        "type": "integer",
                        "description": "Nota académica"
                    },
                    "hash_esperado": {
                        "type": "string",
                        "description": "Hash SHA-256 a verificar"
                    }
                },
                "required": ["dni", "nota", "hash_esperado"]
            }
        }
    }
]


async def auditar_registro(dni: str, nota: int) -> Dict[str, Any]:
    """Execute audit workflow for academic record."""
    state = AcademicAuditState(dni=dni, nota=nota)
    result = await graph.ainvoke(state)
    return {
        "dni": result.get("dni"),
        "nota": result.get("nota"),
        "hash": result.get("hash"),
        "analisis": result.get("analisis"),
        "anomalia_detectada": result.get("anomalia_detectada"),
        "status": result.get("status"),
        "mensaje": result.get("mensaje", "")
    }


async def verificar_hash(dni: str, nota: int, hash_esperado: str) -> Dict[str, Any]:
    """Verify if hash matches the academic record."""
    from agent.tools.crypto import generate_verification_hash
    # Make this truly async by using asyncio.sleep(0) to yield control
    import asyncio
    await asyncio.sleep(0)

    hash_generado = generate_verification_hash(dni, nota)
    coincide = hash_generado == hash_esperado
    return {
        "coincide": coincide,
        "hash_generado": hash_generado,
        "hash_esperado": hash_esperado,
        "mensaje": "✅ Hash verificado correctamente" if coincide else "❌ El hash no coincide"
    }


# Map function names to actual functions
AVAILABLE_FUNCTIONS = {
    "auditar_registro": auditar_registro,
    "verificar_hash": verificar_hash,
}


@traceable(name="conversationalAgent")
async def process_conversation(message: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
    """Process conversational message with tool usage.

    Args:
        message: User message
        history: Previous conversation history

    Returns:
        Assistant response
    """
    from openai import AsyncOpenAI

    if not Config.OPENAI_API_KEY:
        return "⚠️ Error: OPENAI_API_KEY no configurada en .env"

    client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)

    # Build message history
    if history is None:
        history = []

    messages: List[Any] = [
        {
            "role": "system",
            "content": """Eres Nodaris, un asistente de auditoría académica inteligente.

Tu misión:
- Ayudar con auditorías de registros académicos
- Responder preguntas sobre el sistema de notas (escala 0-20)
- Detectar anomalías en calificaciones
- Generar y verificar hashes de autenticación

Capacidades:
- Validar DNI y notas
- Analizar registros académicos
- Detectar posibles inconsistencias
- Generar hashes SHA-256 de verificación

Escala de notas:
- 0-10: Desaprobado
- 11-13: Aprobado
- 14-16: Bueno
- 17-18: Muy bueno
- 19-20: Excelente

Sé profesional, conciso y útil. Usa las herramientas disponibles cuando el usuario necesite auditar o verificar registros."""
        }
    ]

    # Add history
    messages.extend(history)

    # Add current message
    messages.append({"role": "user", "content": message})

    # First LLM call
    response = await client.chat.completions.create(
        model=Config.OPENAI_MODEL,
        messages=messages,
        tools=TOOLS,  # type: ignore
        tool_choice="auto",
        temperature=Config.OPENAI_TEMPERATURE
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    # If no tool calls, return the response
    if not tool_calls:
        return response_message.content or "Lo siento, no pude procesar tu solicitud."

    # Execute tool calls - convert ChatCompletionMessage to dict
    message_dict: Dict[str, Any] = {
        "role": "assistant",
        "content": response_message.content or ""
    }

    # Add tool_calls if present
    if tool_calls:
        message_dict["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,  # type: ignore
                    "arguments": tc.function.arguments  # type: ignore
                }
            } for tc in tool_calls
        ]

    messages.append(message_dict)

    for tool_call in tool_calls:
        function_name = tool_call.function.name  # type: ignore
        function_args = json.loads(tool_call.function.arguments)  # type: ignore

        # Execute the function
        if function_name in AVAILABLE_FUNCTIONS:
            function_to_call = AVAILABLE_FUNCTIONS[function_name]
            function_response = await function_to_call(**function_args)

            # Add function response to messages
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(function_response, ensure_ascii=False)
            })

    # Second LLM call to get final response
    second_response = await client.chat.completions.create(
        model=Config.OPENAI_MODEL,
        messages=messages,
        temperature=Config.OPENAI_TEMPERATURE
    )

    return second_response.choices[0].message.content or "Procesado correctamente."
