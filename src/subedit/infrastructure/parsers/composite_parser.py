import itertools

from ...domain.models.document import Document
from ...domain.models.file_type import FileType
from ...domain.models.prose_unit import ProseUnit
from ...domain.ports.source_parser import ParsedDocument, SourceParser


class CompositeParser(SourceParser[ProseUnit]):
    """One parser over every surface, handing a document to the parser that reads its language."""

    def __init__(self, parsers: tuple[SourceParser[ProseUnit], ...]) -> None:
        claimed = [file_type.language_id for parser in parsers for file_type in parser.file_types]
        if len(claimed) != len(set(claimed)):
            raise ValueError(f'Two parsers claim the same language among {sorted(claimed)}')
        self._parsers = parsers

    @property
    def file_types(self) -> tuple[FileType, ...]:
        return tuple(itertools.chain.from_iterable(parser.file_types for parser in self._parsers))

    def read(self, document: Document) -> ParsedDocument[ProseUnit]:
        parser = self._parser_for(document.language_id)
        return parser.read(document) if parser else ParsedDocument()

    def _parser_for(self, language_id: str) -> SourceParser[ProseUnit] | None:
        return next((parser for parser in self._parsers if parser.supports(language_id)), None)
