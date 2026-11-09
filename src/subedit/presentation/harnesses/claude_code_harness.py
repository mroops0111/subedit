import pathlib
import typing

from .agent_harness import (
    SESSION_START,
    AgentHarness,
    HarnessMetadata,
    Payload,
    ShellCommand,
    context_output,
    existing_source_files,
    session_directory_in,
    shell_command_in,
)


EDIT_TOOLS = frozenset({'Edit', 'Write', 'MultiEdit', 'NotebookEdit'})

_PATH_FIELDS = ('file_path', 'notebook_path')

_CLAUDE_CODE = HarnessMetadata(
    name='claude-code',
    summary='Claude Code names the edited file in tool_input.',
    example={'tool_name': 'Edit', 'tool_input': {'file_path': 'src/module.py'}},
)


class ClaudeCodeHarness(AgentHarness):
    metadata = _CLAUDE_CODE

    def __init__(self, extensions: frozenset[str]) -> None:
        self._extensions = extensions

    def edited_files(self, payload: Payload) -> tuple[pathlib.Path, ...] | None:
        tool_name = payload.get('tool_name')
        if not isinstance(tool_name, str) or tool_name not in EDIT_TOOLS:
            return None
        tool_input = self._tool_input(payload)
        path_values = [tool_input.get(field) for field in _PATH_FIELDS]
        if not any(path_value is not None for path_value in path_values):
            return None
        return existing_source_files(
            [path_value for path_value in path_values if isinstance(path_value, str) and path_value], self._extensions
        )

    def shell_command(self, payload: Payload) -> ShellCommand | None:
        return shell_command_in(payload)

    def session_directory(self, payload: Payload) -> pathlib.Path | None:
        return session_directory_in(payload)

    def session_context_output(self, context: str) -> str:
        return context_output(SESSION_START, context)

    def _tool_input(self, payload: Payload) -> typing.Mapping[str, object]:
        tool_input = payload.get('tool_input')
        return tool_input if isinstance(tool_input, dict) else {}

    def advisory_output(self, advice: str) -> str:
        # Claude Code reads stdout as JSON on exit zero, and adds this field beside the tool result.
        return context_output('PostToolUse', advice)
