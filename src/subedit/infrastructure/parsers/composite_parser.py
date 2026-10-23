from ...domain.models.document import Document
from ...domain.models.position import SourceRange
from ...domain.models.prose_unit import ProseUnit
from ...domain.ports.source_parser import SourceParser


class CompositeParser(SourceParser):
    """One parser over every surface, handing a document to the first parser that reads its language."""

    def __init__(self, parsers: tuple[SourceParser, ...]) -> None:
        self._parsers = parsers

    def supports(self, language_id: str) -> bool:
        return self._parser_for(language_id) is not None

    def parse(self, document: Document) -> tuple[ProseUnit, ...]:
        parser = self._parser_for(document.language_id)
        return parser.parse(document) if parser else ()

    def directive_ranges(self, document: Document) -> tuple[SourceRange, ...]:
        parser = self._parser_for(document.language_id)
        return parser.directive_ranges(document) if parser else ()

    def literal_ranges(self, document: Document) -> tuple[SourceRange, ...]:
        parser = self._parser_for(document.language_id)
        return parser.literal_ranges(document) if parser else ()

    def _parser_for(self, language_id: str) -> SourceParser | None:
        return next((parser for parser in self._parsers if parser.supports(language_id)), None)
