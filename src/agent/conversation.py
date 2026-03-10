"""Conversational agent - thin adapter over the audit graph.

Routes all interactions through the LangGraph workflow,
leveraging the agent_reasoner for tool selection and response generation.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional
from langsmith import traceable

from langchain_core.messages import HumanMessage, AIMessage
from agent.graph.graph import get_graph_with_memory

# Use graph with memory checkpointer for conversation persistence
_graph = get_graph_with_memory()


@traceable(name="conversationalAgent")
async def process_conversation(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    thread_id: str = "default",
) -> str:
    """Process conversational message through the audit graph.

    All interactions (chat, audit requests, file processing) are routed
    through the LangGraph workflow. The agent_reasoner decides which
    tools to use based on the conversation context.

    Args:
        message: User message
        history: Previous conversation history (unused - checkpointer handles persistence)
        thread_id: Thread ID for conversation persistence

    Returns:
        Assistant response string
    """
    config = {"configurable": {"thread_id": thread_id}}

    result = await _graph.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )

    # Return the last AI message (conversational responses)
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content

    # Fall back to report if a full audit was completed
    if result.get("reporte_final"):
        return result["reporte_final"]

    return result.get("mensaje", "Procesado correctamente.")
