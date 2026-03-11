"""Tests for Telegram bot command handlers."""

from __future__ import annotations


class TestListRecentAudits:
    """AuditStore.list_recent_audits returns persisted audit records."""

    def test_returns_empty_when_no_audits(self, tmp_path):
        from agent.storage.audit_store import AuditStore

        store = AuditStore(db_path=str(tmp_path / "test.db"))
        result = store.list_recent_audits(5)
        assert result == []

    def test_returns_recent_audits_ordered_by_newest(self, tmp_path):
        from agent.storage.audit_store import AuditStore

        store = AuditStore(db_path=str(tmp_path / "test.db"))
        state1 = {"status": "success", "confidence_score": 0.9, "hash": "abc123", "dni": "111"}
        state2 = {"status": "success", "confidence_score": 0.8, "hash": "def456", "dni": "222"}
        id1 = store.save_audit(state1, "Report 1")
        id2 = store.save_audit(state2, "Report 2")

        audits = store.list_recent_audits(10)
        assert len(audits) == 2
        # Newest first
        assert audits[0]["id"] == id2
        assert audits[1]["id"] == id1
        assert audits[0]["dni"] == "222"
        assert audits[1]["confidence_score"] == 0.9

    def test_respects_limit(self, tmp_path):
        from agent.storage.audit_store import AuditStore

        store = AuditStore(db_path=str(tmp_path / "test.db"))
        for i in range(5):
            store.save_audit({"status": "success", "dni": str(i)}, f"Report {i}")
        audits = store.list_recent_audits(3)
        assert len(audits) == 3


class TestCommandHandlersExist:
    """Verify that all command handler functions exist and are importable."""

    def test_info_command_exists(self):
        from agent.interfaces.telegram_bot import info_command
        import asyncio
        assert asyncio.iscoroutinefunction(info_command)

    def test_auditorias_command_exists(self):
        from agent.interfaces.telegram_bot import auditorias_command
        import asyncio
        assert asyncio.iscoroutinefunction(auditorias_command)

    def test_stats_command_exists(self):
        from agent.interfaces.telegram_bot import stats_command
        import asyncio
        assert asyncio.iscoroutinefunction(stats_command)

    def test_estado_command_exists(self):
        from agent.interfaces.telegram_bot import estado_command
        import asyncio
        assert asyncio.iscoroutinefunction(estado_command)

    def test_help_command_exists(self):
        from agent.interfaces.telegram_bot import help_command
        import asyncio
        assert asyncio.iscoroutinefunction(help_command)


class TestCommandsMenu:
    """Verify the commands menu constant contains all commands."""

    def test_menu_lists_all_commands(self):
        from agent.interfaces.telegram_bot import _COMMANDS_MENU

        assert "/help" in _COMMANDS_MENU
        assert "/info" in _COMMANDS_MENU
        assert "/auditar" in _COMMANDS_MENU
        assert "/auditorias" in _COMMANDS_MENU
        assert "/stats" in _COMMANDS_MENU
        assert "/estado" in _COMMANDS_MENU
