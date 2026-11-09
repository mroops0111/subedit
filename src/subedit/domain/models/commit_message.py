import dataclasses

from .laid_out_prose import LaidOutProse
from .line_layout import LINE_PREFIX_LAYOUT, LineLayout, PrefixedLine
from .position import SourceRange
from .prose import PLAIN_MARKUP, Prose, ProseMarkup
from .prose_unit import ProseLine, ProseUnit
from .text import TextEdit


@dataclasses.dataclass(frozen=True, slots=True)
class CommitSubject(ProseUnit):
    """The first line of a commit message, which git and every tool after it show alone."""

    range: SourceRange
    # A label before the description, such as a Conventional Commits type or a kernel subsystem,
    # kept apart from the prose.
    prefix: str
    description: str
    # git takes every line up to the first blank one as the subject, so a body needs a blank line above it.
    runs_into_body: bool = False

    @property
    def text(self) -> str:
        return self.prefix + self.description

    @property
    def description_range(self) -> SourceRange:
        start = self.range.start + len(self.prefix.encode('utf-8'))
        return SourceRange(start, self.range.end)

    def prose(self) -> Prose:
        return Prose(self.description)

    def prose_lines(self) -> tuple[ProseLine, ...]:
        return (
            ProseLine(range=self.description_range, text=self.description, opens_paragraph=True, ends_paragraph=True),
        )

    def editable_ranges(self) -> tuple[SourceRange, ...]:
        return (self.description_range,)

    def code_ranges(self) -> tuple[SourceRange, ...]:
        return ()

    def as_edit(self, description: str) -> TextEdit:
        return TextEdit(self.description_range, description)


@dataclasses.dataclass(frozen=True, slots=True)
class CommitBody(LaidOutProse):
    """The paragraphs under a commit message's subject, up to its trailers or the comments git adds."""

    range: SourceRange
    lines: tuple[PrefixedLine, ...]
    layout: LineLayout = LINE_PREFIX_LAYOUT
    markup: ProseMarkup = PLAIN_MARKUP

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError('A commit message body needs at least one line')
