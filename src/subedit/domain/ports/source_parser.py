import abc
import dataclasses
import typing

from ..models.document import Document
from ..models.file_type import FileType
from ..models.position import SourceRange
from ..models.prose_unit import ProseUnit


UnitT = typing.TypeVar('UnitT', bound=ProseUnit, covariant=True)


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedDocument(typing.Generic[UnitT]):
    """What one parse of a document yields, its prose units and the stretches outside them no checker reads."""

    units: tuple[UnitT, ...] = ()
    # Text such as a lint directive or a Markdown code block, which a prose checker has no business reading.
    skipped: tuple[SourceRange, ...] = ()


class SourceParser(abc.ABC, typing.Generic[UnitT]):
    @property
    @abc.abstractmethod
    def file_types(self) -> tuple[FileType, ...]: ...

    @abc.abstractmethod
    def read(self, document: Document) -> ParsedDocument[UnitT]: ...

    def parse(self, document: Document) -> tuple[UnitT, ...]:
        return self.read(document).units

    def supports(self, language_id: str) -> bool:
        return any(file_type.language_id == language_id for file_type in self.file_types)

    def language_id_for(self, extension: str) -> str | None:
        """The language a file is read as, from its extension."""
        return next((file_type.language_id for file_type in self.file_types if extension in file_type.extensions), None)
