"""Static rescue protocols are local planner context, never Backboard documents."""

from pathlib import Path

from brain.tools import RESCUE_PROTOCOLS, SYSTEM_PROMPT


def test_system_prompt_contains_the_local_rescue_protocols():
    assert RESCUE_PROTOCOLS == (Path(__file__).resolve().parent.parent / "knowledge" / "rescue_protocols.md").read_text()
    assert RESCUE_PROTOCOLS in SYSTEM_PROMPT
