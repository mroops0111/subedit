import abc
import dataclasses
import typing

from .position import SourceRange
from .prose import Prose
from .text import TextEdit


@dataclasses.dataclass(frozen=True, slots=True)
class ProseLine:
    """One line of prose as a rule reads it, with no comment delimiter or list marker, and where its text sits."""

    range: SourceRange
    text: str
    # The line starts a list item, whose marker is left out of the text.
    opens_item: bool = False
    # Nothing in the same paragraph follows, so a colon here leads into a list or a block below.
    ends_paragraph: bool = False
    # The line starts a paragraph, so a label may open it.
    opens_paragraph: bool = False

    def span(self, start: int, end: int) -> SourceRange:
        """The source range of the characters from start to end in this line's text."""
        head = len(self.text[:start].encode('utf-8'))
        return SourceRange(self.range.start + head, self.range.start + head + len(self.text[start:end].encode('utf-8')))

    def edit(self, start: int, end: int, new_text: str) -> TextEdit:
        return TextEdit(self.span(start, end), new_text)


class ProseUnit(abc.ABC):
    """A stretch of prose a rule reads, wherever a document holds it, such as a comment or a Markdown paragraph."""

    __slots__ = ()

    # The name a rule reference gives the rules that read this kind of unit,
    # so a new surface heads its own section with no change to the reference.
    surface_name: typing.ClassVar[str] = 'Every Surface'

    range: SourceRange

    @abc.abstractmethod
    def prose(self) -> Prose: ...

    @abc.abstractmethod
    def prose_lines(self) -> tuple[ProseLine, ...]:
        """The lines that hold prose, leaving out code and sections a tool reads, so a rule can edit them in place."""

    @abc.abstractmethod
    def editable_ranges(self) -> tuple[SourceRange, ...]:
        """Where an outside checker may edit, which leaves out what shares a line with code or markup."""

    @abc.abstractmethod
    def code_ranges(self) -> tuple[SourceRange, ...]:
        """Where the unit holds code, which a prose checker has no business reading."""

    @property
    def renders_markup(self) -> bool:
        """Whether a reader sees the text rendered, so bold shows as bold instead of as asterisks."""
        return False

    @property
    def is_heading(self) -> bool:
        return False

    @property
    def is_quoted(self) -> bool:
        """Whether the text quotes someone else's words, which punctuation rules leave as written."""
        return False
