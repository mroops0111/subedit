import abc

from ..models.document import Document
from ..models.position import SourceRange
from ..models.prose_unit import ProseUnit


class SourceParser(abc.ABC):
    @abc.abstractmethod
    def supports(self, language_id: str) -> bool: ...

    @abc.abstractmethod
    def parse(self, document: Document) -> tuple[ProseUnit, ...]: ...

    def directive_ranges(self, document: Document) -> tuple[SourceRange, ...]:
        """Where a comment holds a directive such as eslint-disable or noqa, which a tool reads instead of a person."""
        return ()

    def literal_ranges(self, document: Document) -> tuple[SourceRange, ...]:
        """Where a document holds text that is no prose, such as Markdown's front matter, code, and tables."""
        return ()
