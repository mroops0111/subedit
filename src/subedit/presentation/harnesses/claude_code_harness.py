import json
import pathlib
import re
import typing

from .agent_harness import AgentHarness, HarnessMetadata, Payload, existing_source_files


# The tools and events of Claude Code's that the hook acts on.
EDIT_TOOLS = frozenset({'Edit', 'Write', 'MultiEdit', 'NotebookEdit'})
SHELL_TOOL = 'Bash'
SESSION_START = 'SessionStart'

_PATH_FIELDS = ('file_path', 'notebook_path')

_CLAUDE_CODE = HarnessMetadata(
    name='claude-code',
    summary='Claude Code names the edited file in tool_input.',
    example={'tool_name': 'Edit', 'tool_input': {'file_path': 'src/module.py'}},
)

# git takes its own options before the subcommand, and -C among them moves where it runs.
_GIT_COMMIT = re.compile(r'(?:^|[\s;&|(])git((?:\s+(?:-C\s+\S+|-c\s+\S+|--?[\w-]+(?:=\S+)?))*)\s+commit(?=\s|$|[;&|)])')
_CHANGE_DIRECTORY = re.compile(r'-C\s+(\S+)')


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

    def commit_directory(self, payload: Payload) -> pathlib.Path | None:
        if payload.get('tool_name') != SHELL_TOOL:
            return None
        command = self._tool_input(payload).get('command')
        commit = _GIT_COMMIT.search(command) if isinstance(command, str) else None
        if commit is None:
            return None
        directory = self._working_directory(payload)
        for moved in _CHANGE_DIRECTORY.finditer(commit.group(1)):
            directory = directory / moved.group(1).strip('\'"')
        return directory

    def session_directory(self, payload: Payload) -> pathlib.Path | None:
        return self._working_directory(payload) if payload.get('hook_event_name') == SESSION_START else None

    def session_output(self, context: str) -> str:
        return json.dumps({'hookSpecificOutput': {'hookEventName': SESSION_START, 'additionalContext': context}})

    def _working_directory(self, payload: Payload) -> pathlib.Path:
        directory = payload.get('cwd')
        return pathlib.Path(directory) if isinstance(directory, str) and directory else pathlib.Path.cwd()

    def _tool_input(self, payload: Payload) -> typing.Mapping[str, object]:
        tool_input = payload.get('tool_input')
        return tool_input if isinstance(tool_input, dict) else {}

    def advisory_output(self, advice: str) -> str:
        # Claude Code reads stdout as JSON on exit zero, and adds this field beside the tool result.
        return json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': advice}})
