"""Memory manager for Nodaris agent.

Manages conversation history and context for the agent.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MemoryEntry:
    """Single memory entry."""

    timestamp: datetime
    user_input: str
    agent_response: str
    context: Dict = field(default_factory=dict)


class MemoryManager:
    """Manages agent memory across conversations."""

    def __init__(self, max_entries: int = 100):
        """Initialize memory manager.

        Args:
            max_entries: Maximum number of entries to keep in memory
        """
        self.max_entries = max_entries
        self._entries: List[MemoryEntry] = []

    def add_entry(
        self,
        user_input: str,
        agent_response: str,
        context: Optional[Dict] = None
    ) -> None:
        """Add a new memory entry.

        Args:
            user_input: User's input
            agent_response: Agent's response
            context: Additional context information
        """
        entry = MemoryEntry(
            timestamp=datetime.now(),
            user_input=user_input,
            agent_response=agent_response,
            context=context or {}
        )

        self._entries.append(entry)

        # Trim old entries if exceeding max
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

    def get_recent(self, n: int = 5) -> List[MemoryEntry]:
        """Get the n most recent entries.

        Args:
            n: Number of recent entries to retrieve

        Returns:
            List of recent memory entries
        """
        return self._entries[-n:] if self._entries else []

    def clear(self) -> None:
        """Clear all memory entries."""
        self._entries.clear()

    def get_context_summary(self) -> str:
        """Generate a summary of recent conversation context.

        Returns:
            String summary of recent context
        """
        recent = self.get_recent(3)
        if not recent:
            return "No previous conversation context."

        summary_parts = []
        for entry in recent:
            summary_parts.append(
                f"User: {entry.user_input[:100]}...\n"
                f"Assistant: {entry.agent_response[:100]}..."
            )

        return "\n\n".join(summary_parts)
