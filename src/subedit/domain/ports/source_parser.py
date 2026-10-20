import abc

from ..models.comment import CommentGroup
from ..models.document import Document
from ..models.position import SourceRange


class SourceParser(abc.ABC):
    @abc.abstractmethod
    def supports(self, language_id: str) -> bool: ...

    @abc.abstractmethod
    def parse(self, document: Document) -> tuple[CommentGroup, ...]: ...

    def directive_ranges(self, document: Document) -> tuple[SourceRange, ...]:
        """Where a comment holds a directive such as eslint-disable or noqa, which a tool reads instead of a person."""
        return ()
