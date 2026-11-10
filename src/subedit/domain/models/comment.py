import dataclasses
import enum

from .laid_out_prose import LaidOutProse
from .line_layout import LINE_PREFIX_LAYOUT, LineLayout, PrefixedLine
from .position import SourceRange
from .prose import PLAIN_MARKUP, ProseMarkup


class CommentForm(enum.Enum):
    LINE = 'line'
    BLOCK = 'block'
    DOC = 'doc'


class CommentPlacement(enum.Enum):
    FILE_HEADER = 'file-header'
    LEADING_DECLARATION = 'leading-declaration'
    INLINE_BODY = 'inline-body'
    TRAILING = 'trailing'


class Visibility(enum.Enum):
    PUBLIC = 'public'
    INTERNAL = 'internal'


class SymbolKind(enum.Enum):
    MODULE = 'module'
    CLASS = 'class'
    FUNCTION = 'function'


@dataclasses.dataclass(frozen=True, slots=True)
class SymbolRef:
    """The declaration a comment documents, and whether other code can see it."""

    name: str
    kind: SymbolKind
    visibility: Visibility
    # A comment over several declarations, right under code, may head them as a group rather than document this one.
    may_head_a_group: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class CommentGroup(LaidOutProse):
    """Consecutive comment lines that read as one block, with what they document and how they are laid out."""

    range: SourceRange
    lines: tuple[PrefixedLine, ...]
    form: CommentForm
    placement: CommentPlacement
    attachment: SymbolRef | None = None
    layout: LineLayout = LINE_PREFIX_LAYOUT
    markup: ProseMarkup = PLAIN_MARKUP

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError('A comment group needs at least one line')
        if self.attachment is not None and self.placement is not CommentPlacement.LEADING_DECLARATION:
            raise ValueError(
                f'Only a leading declaration comment documents a symbol, '
                f'but a {self.placement.value} comment carries {self.attachment.name!r}'
            )

    @property
    def statistics_category(self) -> str:
        if self.form is CommentForm.DOC:
            visibility = Visibility.PUBLIC if self.attaches_to_public_symbol else Visibility.INTERNAL
            return f'doc/{visibility.value}'
        if self.placement is CommentPlacement.FILE_HEADER:
            return 'plain/file-header'
        return f'plain/{self.placement.value}'

    @property
    def attaches_to_public_symbol(self) -> bool:
        return self.attachment is not None and self.attachment.visibility is Visibility.PUBLIC

    @property
    def stays_on_its_line(self) -> bool:
        """A trailing comment shares its line with code, so a second line would have no code to sit beside."""
        return self.placement is CommentPlacement.TRAILING

    def keeps_its_layout(self, width: int) -> bool:
        """A one line docstring that fits is the summary convention, not a block to lay out."""
        one_line_doc = self.form is CommentForm.DOC and self.line_count == 1 and self.longest_line <= width
        return self.stays_on_its_line or one_line_doc

    @property
    def renders_markup(self) -> bool:
        """A docstring or a JSDoc block is rendered on hover and in generated docs, while a line comment is not."""
        return self.form is CommentForm.DOC
