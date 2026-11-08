import abc
import pathlib

from .harnesses import ShellCommand


class AgentWrite(abc.ABC):
    """Text an agent wrote that the hook checks, and how a fixed version of it reaches where it lives."""

    @property
    @abc.abstractmethod
    def path(self) -> pathlib.Path:
        """The file the text is read as, which picks its surface, resolves its config, and names it in a finding."""
        ...

    @abc.abstractmethod
    def read(self) -> str | None: ...

    @abc.abstractmethod
    def write_back(self, text: str) -> str | None:
        """Put the fixed text in place, or return what the agent must do where the hook cannot write it."""
        ...


class EditedFile(AgentWrite):
    """A file an agent edited, which the hook fixes in place."""

    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    @property
    def path(self) -> pathlib.Path:
        return self._path

    def read(self) -> str | None:
        try:
            return self._path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return None

    def write_back(self, text: str) -> str | None:
        self._path.write_text(text, encoding='utf-8')
        return None


class ShellWatcher(abc.ABC):
    """Recognises a shell command that wrote text some surface reads, and hands that text to the hook."""

    @property
    @abc.abstractmethod
    def keyword(self) -> str:
        """A word every command this watcher reads contains, which lets the plugin skip the rest before starting."""
        ...

    @abc.abstractmethod
    def writes(self, command: ShellCommand) -> tuple[AgentWrite, ...]: ...
