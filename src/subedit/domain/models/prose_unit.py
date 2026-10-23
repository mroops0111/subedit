import abc

from .position import SourceRange
from .prose import Prose


class ProseUnit(abc.ABC):
    """A stretch of prose a rule reads, wherever a document holds it, such as a comment or a Markdown paragraph."""

    __slots__ = ()

    range: SourceRange

    @abc.abstractmethod
    def prose(self) -> Prose: ...

    @abc.abstractmethod
    def editable_ranges(self) -> tuple[SourceRange, ...]:
        """Where an outside checker may edit, which leaves out what shares a line with code or markup."""

    @abc.abstractmethod
    def code_ranges(self) -> tuple[SourceRange, ...]:
        """Where the unit holds code, which a prose checker has no business reading."""
