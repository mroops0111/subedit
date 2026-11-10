import abc
import pathlib


class AgentWrittenText(abc.ABC):
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


class EditedFile(AgentWrittenText):
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
