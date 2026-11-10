import abc

from ..agent_written_text import AgentWrittenText
from ..harnesses import ShellCommand


class ShellCommandReader(abc.ABC):
    """Recognises a shell command that wrote text some surface reads, and hands that text to the hook."""

    @property
    @abc.abstractmethod
    def keyword(self) -> str:
        """A word every command this reader reads contains, which lets the plugin skip the rest before starting."""
        ...

    @abc.abstractmethod
    def written_texts(self, command: ShellCommand) -> tuple[AgentWrittenText, ...]: ...
