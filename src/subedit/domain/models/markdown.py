import dataclasses
import enum
import itertools
import re
import typing
import unicodedata

from .position import SourceRange
from .prose import Prose, is_wide
from .prose_unit import ProseLine, ProseUnit
from .text import TextEdit


# Two trailing spaces, a backslash, or a <br> tag ask for a line break, so the author meant it.
_HARD_BREAK = re.compile(r'( {2,}|\\|<br\s*/?>)$', re.IGNORECASE)


class MarkdownBlockKind(enum.Enum):
    HEADING = 'heading'
    PARAGRAPH = 'paragraph'


@dataclasses.dataclass(frozen=True, slots=True)
class MarkdownLine:
    """One source line of a block, its text apart from the indent or quote marker that carries it inside a container."""

    range: SourceRange
    text: str
    prefix: str = ''

    @property
    def ends_in_hard_break(self) -> bool:
        return _HARD_BREAK.search(self.text) is not None


@dataclasses.dataclass(frozen=True, slots=True)
class MarkdownBlock(ProseUnit):
    """A heading or paragraph of a Markdown document, ranging over its text from the first character to the last."""

    surface_name: typing.ClassVar[str] = 'Markdown'

    range: SourceRange
    kind: MarkdownBlockKind
    lines: tuple[MarkdownLine, ...]
    level: int = 0
    list_depth: int = 0
    # The paragraph is the first in its list item, so its first line carries the item's marker.
    opens_item: bool = False
    quoted: bool = False
    # A heading whose section opens straight into a list, with no sentence to frame it.
    leads_into_list: bool = False

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError('A Markdown block needs at least one line')
        if self.lines[0].prefix:
            raise ValueError('A block starts at its text, so its first line carries no prefix')

    @property
    def text(self) -> str:
        return self.lines[0].text + ''.join('\n' + line.prefix + line.text for line in self.lines[1:])

    def prose(self) -> Prose:
        return Prose(self.joined())

    def prose_lines(self) -> tuple[ProseLine, ...]:
        last = len(self.lines) - 1
        return tuple(
            ProseLine(
                range=line.range,
                text=line.text,
                opens_item=self.opens_item and index == 0,
                ends_paragraph=index == last,
                opens_paragraph=index == 0,
            )
            for index, line in enumerate(self.lines)
        )

    def editable_ranges(self) -> tuple[SourceRange, ...]:
        return tuple(line.range for line in self.lines)

    @property
    def renders_markup(self) -> bool:
        return True

    @property
    def is_heading(self) -> bool:
        return self.kind is MarkdownBlockKind.HEADING

    @property
    def is_quoted(self) -> bool:
        return self.quoted

    def code_ranges(self) -> tuple[SourceRange, ...]:
        return ()

    @property
    def soft_break_count(self) -> int:
        return sum(1 for line in self.lines[:-1] if not line.ends_in_hard_break)

    def joined(self) -> str:
        """The block with every soft line break closed up, so a paragraph reads as the one line it renders as."""
        joined = self.lines[0].text
        for previous, line in itertools.pairwise(self.lines):
            if previous.ends_in_hard_break:
                joined += '\n' + line.prefix + line.text
                continue
            head, tail = joined.rstrip(), line.text.lstrip()
            joined = head + _joiner(head[-1:], tail[:1]) + tail
        return joined

    def as_edit(self, new_text: str) -> TextEdit:
        return TextEdit(self.range, new_text)


# A line break inside Chinese or Japanese text renders as nothing, and anywhere else as a space,
# and no space sits beside full-width punctuation.
def _joiner(before: str, after: str) -> str:
    if is_wide(before) and is_wide(after):
        return ''
    if _is_wide_punctuation(before) or _is_wide_punctuation(after):
        return ''
    return ' '


def _is_wide_punctuation(character: str) -> bool:
    return is_wide(character) and unicodedata.category(character).startswith('P')
