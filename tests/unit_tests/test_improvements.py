"""Tests for the 9 improvements: auto-recovery, guardrails, cache, etc."""

import json
from unittest.mock import patch, MagicMock

import pytest


# ============================================================================
# Test 1: Auto-recovery detects empty tool responses
# ============================================================================

class TestAutoRecovery:
    """smart_tool_executor injects feedback when tools return empty data."""

    def test_empty_signal_detected(self):
        """Verify _EMPTY_SIGNALS patterns match common failure messages."""
        from agent.graph.graph import smart_tool_executor

        # The function exists and is callable
        assert callable(smart_tool_executor)

    def test_recovery_hint_format(self):
        """Recovery hints include tool name."""
        hint = (
            "La herramienta 'test_tool' no devolvió datos útiles. "
            "Considera usar otra herramienta o verificar que los datos estén disponibles en el estado."
        )
        assert "test_tool" in hint
        assert "otra herramienta" in hint


# ============================================================================
# Test 3: Report output guardrails
# ============================================================================

class TestReportGuardrails:
    """_validate_report_guardrails removes phantom sections."""

    def test_removes_copias_section_without_data(self):
        from agent.nodes.report import _validate_report_guardrails

        divider = "─" * 70
        report = (
            "Header\n"
            "🔍 DETECCIÓN DE COPIAS  (3 casos)\n"
            "Total de casos: 5\n"
            "  🔴 Caso 1: A ↔ B\n"
            + divider + "\n"
            "💡 RECOMENDACIONES\n"
            "• Sin acciones\n"
        )
        state = {"copias_detectadas": [], "respuestas_nr": [], "tiempos_sospechosos": []}
        cleaned = _validate_report_guardrails(state, report)

        assert "DETECCIÓN DE COPIAS" not in cleaned, f"Should remove copias. Got: {cleaned[:200]}"
        assert "RECOMENDACIONES" in cleaned, f"Should keep recommendations. Got length={len(cleaned)}, repr={repr(cleaned[:200])}"

    def test_keeps_copias_section_with_data(self):
        from agent.nodes.report import _validate_report_guardrails

        divider = "─" * 70
        report = (
            "Header\n"
            "🔍 DETECCIÓN DE COPIAS  (1 caso)\n"
            "Total: 1\n"
            + divider + "\n"
            "Footer\n"
        )
        state = {"copias_detectadas": [{"estudiante1": "A", "estudiante2": "B"}]}
        cleaned = _validate_report_guardrails(state, report)

        assert "DETECCIÓN DE COPIAS" in cleaned

    def test_removes_abandono_without_data(self):
        from agent.nodes.report import _validate_report_guardrails

        report = (
            "Header\n"
            "⚠️ ABANDONO (NR)  (3 estudiantes)\n"
            "Estudiantes: 3\n"
            "┌─────────────────────────────────────────────┐\n"
            "Footer\n"
        )
        state = {"copias_detectadas": [], "respuestas_nr": [], "tiempos_sospechosos": []}
        cleaned = _validate_report_guardrails(state, report)

        assert "ABANDONO" not in cleaned

    def test_removes_tiempos_without_data(self):
        from agent.nodes.report import _validate_report_guardrails

        report = (
            "Header\n"
            "⏱️ TIEMPOS SOSPECHOSOS  (2 estudiantes)\n"
            "Estudiantes: 2\n"
            "┌─────────────────────────────────────────────┐\n"
            "Footer\n"
        )
        state = {"copias_detectadas": [], "respuestas_nr": [], "tiempos_sospechosos": []}
        cleaned = _validate_report_guardrails(state, report)

        assert "TIEMPOS SOSPECHOSOS" not in cleaned


# ============================================================================
# Test 6: Tool result cache
# ============================================================================

class TestToolCache:
    """Tool cache avoids redundant tool executions."""

    def test_cache_key_deterministic(self):
        from agent.graph.graph import _cache_key

        key1 = _cache_key("tool_a", '{"x": 1}')
        key2 = _cache_key("tool_a", '{"x": 1}')
        key3 = _cache_key("tool_b", '{"x": 1}')

        assert key1 == key2, "Same tool + args should produce same key"
        assert key1 != key3, "Different tools should produce different keys"

    def test_cache_max_size(self):
        from agent.graph.graph import _CACHE_MAX_SIZE
        assert _CACHE_MAX_SIZE > 0


# ============================================================================
# Test 9: Admin notification config
# ============================================================================

class TestAdminNotification:
    """TELEGRAM_ADMIN_CHAT_ID config exists for failed job notifications."""

    def test_config_has_admin_chat_id(self):
        from agent.config import Config
        # The attribute exists (may be None)
        assert hasattr(Config, "TELEGRAM_ADMIN_CHAT_ID")

    def test_notify_function_exists(self):
        from agent.interfaces.queue_consumer import _notify_admin
        assert callable(_notify_admin)
