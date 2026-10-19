import pathlib

from ...infrastructure import EXTENSIONS
from .agent_harness import BLOCK_EXIT, AgentHarness, HarnessMetadata, Payload
from .claude_code_harness import ClaudeCodeHarness
from .codex_harness import CodexHarness


# Each agent names its edit tools differently, so a payload identifies its own sender.
# One project can run both agents at once, and neither needs to know the other exists.
ALL_HARNESSES: tuple[AgentHarness, ...] = (
    ClaudeCodeHarness(EXTENSIONS),
    CodexHarness(EXTENSIONS),
)


def resolve(payload: Payload) -> tuple[AgentHarness, tuple[pathlib.Path, ...]] | None:
    """Hand the payload to each harness until one recognises it.

    A harness that declines returns None, so declining and finding nothing stay distinct.
    """
    for harness in ALL_HARNESSES:
        edited_paths = harness.edited_files(payload)
        if edited_paths is not None:
            return harness, edited_paths
    return None


__all__ = [
    'ALL_HARNESSES',
    'BLOCK_EXIT',
    'AgentHarness',
    'ClaudeCodeHarness',
    'CodexHarness',
    'HarnessMetadata',
    'Payload',
    'resolve',
]
