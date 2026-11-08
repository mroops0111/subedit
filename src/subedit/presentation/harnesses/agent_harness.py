import abc
import dataclasses
import json
import pathlib
import typing


# Both Claude Code and Codex block by exiting two and writing the reason to stderr,
# so the exit contract is shared and only the payload shape differs.
BLOCK_EXIT = 2
# Both name their shell tool and the session's opening event alike.
SHELL_TOOL = 'Bash'
SESSION_START = 'SessionStart'

Payload = typing.Mapping[str, object]


@dataclasses.dataclass(frozen=True, slots=True)
class HarnessMetadata:
    name: str
    summary: str
    example: Payload

    def __post_init__(self) -> None:
        if not self.name or not self.summary:
            raise ValueError('A harness names itself and says what it recognises')


@dataclasses.dataclass(frozen=True, slots=True)
class ShellCommand:
    """A command an agent ran in the shell, and the directory it ran in."""

    command: str
    directory: pathlib.Path


class AgentHarness(abc.ABC):
    """One agent's way of telling the hook what it edited, ran, or opened, and of hearing back."""

    metadata: HarnessMetadata

    @abc.abstractmethod
    def edited_files(self, payload: Payload) -> tuple[pathlib.Path, ...] | None:
        """Return the files this payload edited, or None when it came from another agent.

        An empty tuple and None mean different things.
        Empty says the payload was ours and touched nothing we check.
        None says it was never ours to read.
        """
        ...

    def shell_command(self, payload: Payload) -> ShellCommand | None:
        """The command this payload ran in the shell, or None for any other payload."""
        return None

    def session_directory(self, payload: Payload) -> pathlib.Path | None:
        """The directory a session opened in when this payload starts one, or None for any other payload."""
        return None

    def session_output(self, context: str) -> str:
        """Stdout that puts context in front of the model as a session opens, or nothing where the agent has none."""
        return ''

    def advisory_output(self, advice: str) -> str:
        """Stdout that puts advice in front of the model without blocking, or nothing where the agent has no channel.

        Exit two is the only shared way to reach the model, and it blocks, so a warning needs one of its own.
        """
        return ''


def existing_source_files(
    candidates: typing.Iterable[str | pathlib.Path], extensions: frozenset[str]
) -> tuple[pathlib.Path, ...]:
    paths = [pathlib.Path(candidate) for candidate in candidates]
    return tuple(dict.fromkeys(path for path in paths if path.suffix in extensions and path.is_file()))


def shell_command_in(payload: Payload) -> ShellCommand | None:
    """The shell command of a payload shaped as Claude Code and Codex both send one."""
    tool_input = payload.get('tool_input')
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    if payload.get('tool_name') != SHELL_TOOL or not isinstance(command, str):
        return None
    return ShellCommand(command, working_directory(payload))


def session_directory_in(payload: Payload) -> pathlib.Path | None:
    """The directory of a session start shaped as Claude Code and Codex both send one."""
    return working_directory(payload) if payload.get('hook_event_name') == SESSION_START else None


def context_output(event_name: str, context: str) -> str:
    """Stdout that both agents add to the model's context for the event, on exit zero."""
    return json.dumps({'hookSpecificOutput': {'hookEventName': event_name, 'additionalContext': context}})


def working_directory(payload: Payload) -> pathlib.Path:
    directory = payload.get('cwd')
    return pathlib.Path(directory) if isinstance(directory, str) and directory else pathlib.Path.cwd()
