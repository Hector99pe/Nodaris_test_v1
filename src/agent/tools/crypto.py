"""Cryptographic utilities for verification."""

import hashlib
from langsmith import traceable
from langchain_core.tools import tool as langgraph_tool


@traceable(name="generateHash")
def generate_verification_hash(dni: str, nota: int) -> str:
    """Generate SHA-256 verification hash for academic record.

    Args:
        dni: Student identification number
        nota: Academic grade

    Returns:
        Hexadecimal SHA-256 hash string
    """
    texto = dni + str(nota)
    return hashlib.sha256(texto.encode()).hexdigest()


# === LangGraph Tool Wrapper ===

@langgraph_tool
def tool_generar_hash(dni: str, nota: int) -> str:
    """Genera un hash SHA-256 de verificación para un registro académico individual.

    Args:
        dni: DNI del estudiante (8 dígitos)
        nota: Nota académica (0-20)
    """
    hash_value = generate_verification_hash(dni, nota)
    return f"Hash SHA-256 generado: {hash_value}"
