import pathlib
import re
import typing

from .agent_harness import AgentHarness, HarnessMetadata, Payload, existing_source_files


EDIT_TOOLS = frozenset({'apply_patch'})

_CODEX = HarnessMetadata(
    name='codex',
    summary='Codex sends a patch, and the path is read from its header.',
    example={'tool_name': 'apply_patch', 'tool_input': {'command': '*** Update File: src/module.py'}},
)


# Codex carries no path field.
# The patch body names each file in its header, so the path is read back out of the diff.
_PATCH_HEADER = re.compile(r'^(?:\*\*\*\s+(?:Update|Add|Delete) File:|---|\+\+\+)\s+(.+?)\s*$', re.MULTILINE)
_STRIP_PREFIX = re.compile(r'^[ab]/')


class CodexHarness(AgentHarness):
    metadata = _CODEX

    def __init__(self, extensions: frozenset[str]) -> None:
        self._extensions = extensions

    def edited_files(self, payload: Payload) -> tuple[pathlib.Path, ...] | None:
        tool_name = payload.get('tool_name')
        if not isinstance(tool_name, str) or tool_name not in EDIT_TOOLS:
            return None
        command = self._tool_input(payload).get('command')
        if not isinstance(command, str):
            return None
        patched_paths = [_STRIP_PREFIX.sub('', header.group(1)) for header in _PATCH_HEADER.finditer(command)]
        return existing_source_files(
            [patched_path for patched_path in patched_paths if patched_path != '/dev/null'], self._extensions
        )

    def _tool_input(self, payload: Payload) -> typing.Mapping[str, object]:
        tool_input = payload.get('tool_input')
        return tool_input if isinstance(tool_input, dict) else {}
