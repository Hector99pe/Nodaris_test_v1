import re
from pathlib import Path

from agent.tools.prompts import build_agent_system_prompt, load_instinct, load_soul


def test_soul_file_is_loaded() -> None:
    soul = load_soul()
    assert "Nodaris" in soul
    assert "Hard Limits" in soul


def test_instinct_file_is_loaded() -> None:
    instinct = load_instinct()
    assert "Behavioral Instincts" in instinct
    assert "Formal Rule Precedence" in instinct


def test_agent_system_prompt_uses_soul_and_context() -> None:
    prompt = build_agent_system_prompt("demo-context")
    assert "Instintos operativos (instinct.md):" in prompt
    assert "Contexto actual:" in prompt
    assert "demo-context" in prompt
    assert "Nodaris" in prompt


def test_system_prompt_includes_formal_precedence() -> None:
    prompt = build_agent_system_prompt("contexto")
    assert "Formal Rule Precedence" in prompt
    assert "Hard Limits" in prompt


def test_no_hardcoded_system_prompt_in_nodes() -> None:
    """Prevent prompt drift: system identity must come from SOUL.md."""
    repo_root = Path(__file__).resolve().parents[2]
    nodes_dir = repo_root / "src" / "agent" / "nodes"

    disallowed_patterns = [
        r"AGENT_SYSTEM_PROMPT\s*=",
        r"SystemMessage\(\s*content\s*=\s*f?[\"']",
        r"\"role\"\s*:\s*\"system\"",
    ]

    violations: list[str] = []

    for py_file in sorted(nodes_dir.glob("*.py")):
        if py_file.name == "analysis.py":
            # Legacy node kept for reference; active graph does not route through it.
            continue

        text = py_file.read_text(encoding="utf-8")
        for pattern in disallowed_patterns:
            if re.search(pattern, text):
                violations.append(f"{py_file.name}: pattern '{pattern}'")

    assert not violations, (
        "Se detectaron prompts hardcodeados en nodos. "
        "Usa agent.tools.prompts.build_agent_system_prompt() y SOUL.md. "
        f"Violaciones: {violations}"
    )
