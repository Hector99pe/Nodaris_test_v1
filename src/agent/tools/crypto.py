"""Cryptographic utilities for verification."""

import hashlib
from langsmith import traceable


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
