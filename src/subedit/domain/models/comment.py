import dataclasses
import enum
import itertools

from .comment_layout import LINE_LAYOUT, CommentLayout, CommentLine
from .position import SourceRange
from .prose import PLAIN_MARKUP, Prose, ProseMarkup, Sentence, break_cost, comma_breaks, reflow_sentence
from .prose_unit import ProseUnit
from .text import TextEdit


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
    name: str
    kind: SymbolKind
    visibility: Visibility
    # A comment over several declarations, right under code, may head them as a group rather than document this one.
    may_head_a_group: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class CommentGroup(ProseUnit):
    range: SourceRange
    lines: tuple[CommentLine, ...]
    form: CommentForm
    placement: CommentPlacement
    attachment: SymbolRef | None = None
    layout: CommentLayout = LINE_LAYOUT
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
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def longest_line(self) -> int:
        return max(line.physical_width for line in self.lines)

    @property
    def has_summary_line(self) -> bool:
        """Whether the first sentence is a one-line summary, as a style guide such as PEP 257 asks."""
        return self.layout.summary_convention is not None

    @property
    def attaches_to_public_symbol(self) -> bool:
        return self.attachment is not None and self.attachment.visibility is Visibility.PUBLIC

    def prose(self) -> Prose:
        filled_lines = [line for line in self.lines if line.text.strip()]
        base = min((len(line.indent) for line in filled_lines), default=0)
        rendered_lines = [
            ' ' * max(0, len(line.indent) - base) + line.text.rstrip() if line.text.strip() else ''
            for line in self.lines
        ]
        return Prose('\n'.join(rendered_lines), self.markup)

    def editable_ranges(self) -> tuple[SourceRange, ...]:
        """A trailing comment shares its line with code, so only a comment standing on its own lines is editable."""
        if self.placement is CommentPlacement.TRAILING:
            return ()
        return tuple(line.range for line in self.lines)

    def code_ranges(self) -> tuple[SourceRange, ...]:
        """Where the lines holding code sit, which a prose checker has no business reading."""
        return tuple(self.lines[index].range for index in sorted(self.prose().code_line_indexes()))

    def reflow(self, width: int, stub_floor: int = 0) -> 'CommentGroup':
        # A trailing comment shares its line with code, so a second line would have no code to sit beside.
        if self.placement is CommentPlacement.TRAILING:
            return self
        # A one line docstring that fits is the summary convention, not a block to lay out.
        if self.form is CommentForm.DOC and self.line_count == 1 and self.longest_line <= width:
            return self
        texts = self._reflow_into_texts(width, stub_floor)
        # Text that ends up on one line closes there too, so the closing quotes need room beside it.
        closing_width = len(self.closing())
        if len(texts) == 1 and len(texts[0]) > self.text_budget(width, first_line=True) - closing_width:
            texts = self._reflow_into_texts(width, stub_floor, closing_width)
        if not texts:
            return self
        rebuilt = dataclasses.replace(self, lines=self.layout.rebuild(self.lines, texts, width))
        # A sentence with no legal break may come out longer than the author wrapped it,
        # and a fix that pushes a line past the width trades one finding for another.
        if rebuilt.longest_line > max(width, self.longest_line):
            return self
        return rebuilt

    def sentences_held_by_a_list(self, width: int, stub_floor: int = 0) -> tuple[str, ...]:
        """The sentences reflow leaves as the author broke them, since every legal break would split a list."""
        held: list[str] = []
        self._reflow_into_texts(width, stub_floor, held=held)
        return tuple(held)

    def text_budget(self, width: int, *, first_line: bool) -> int:
        """The characters of text a line holds, which on a docstring's opening line also cede the quotes."""
        return self.layout.text_budget(self.lines, width, first_line=first_line)

    # A sentence takes as few lines as fit, and the author's layout stays when it breaks no worse than the best one.
    # A sentence whose new layout would strand a stub, split a list, or still overflow needs its author,
    # so it keeps the layout they gave it rather than one its own check rejects.
    # A summary never breaks where the comment's style guide keeps it to one line.
    def _reflow_into_texts(
        self, width: int, stub_floor: int, reserve: int = 0, held: list[str] | None = None
    ) -> tuple[str, ...]:
        body_budget = self.text_budget(width, first_line=False)
        out: list[str] = []
        for paragraph_index, (paragraph, is_literal, follows_blank) in enumerate(self._split_into_paragraphs()):
            if out and (follows_blank or self.layout.parts_every_paragraph):
                out.append('')
            if is_literal:
                out.extend(paragraph)
                continue
            lines = tuple(line.strip() for line in paragraph if line.strip())
            sentences = Prose(' '.join(lines)).sentences()
            shared_until = 0
            for sentence_index, sentence in enumerate(sentences):
                if sentence.offset < shared_until:
                    continue
                if sentence_index == 1 and paragraph_index == 0 and self.has_summary_line:
                    out.append('')
                first_budget = self.text_budget(width, first_line=not out) - (reserve if not out else 0)
                is_summary = self.has_summary_line and paragraph_index == 0 and sentence_index == 0
                shared_line = None if is_summary else _shared_line(lines, sentences[sentence_index:])
                if shared_line is not None and len(shared_line) <= first_budget:
                    out.append(shared_line)
                    shared_until = sentence.offset + len(shared_line)
                    continue
                if is_summary:
                    best_lines: tuple[str, ...] = (sentence.text,)
                else:
                    best_lines = reflow_sentence(sentence.text, body_budget, stub_floor, first_width=first_budget)
                given_lines = _given_lines(lines, sentence)
                if given_lines and _keeps_given(given_lines, best_lines, (first_budget, body_budget), stub_floor):
                    out.extend(given_lines)
                elif _is_legal(best_lines, (first_budget, body_budget), stub_floor) and not (
                    given_lines and break_cost(best_lines)
                ):
                    out.extend(best_lines)
                elif given_lines:
                    if held is not None and _is_legal(best_lines, (first_budget, body_budget), stub_floor):
                        held.append(sentence.text)
                    out.extend(given_lines)
                elif _strands_stub(best_lines, stub_floor):
                    return ()
                else:
                    out.extend(best_lines)
        return tuple(out)

    def _split_into_paragraphs(self) -> tuple[tuple[tuple[str, ...], bool, bool], ...]:
        """Each paragraph's lines, whether they are literal, and whether a blank line comes before them."""
        paragraphs: list[tuple[tuple[str, ...], bool, bool]] = []
        follows_blank = False
        for segment in self.prose().segments():
            current_lines: list[str] = []
            for line in segment.lines:
                if line.strip():
                    current_lines.append(line)
                    continue
                if current_lines:
                    paragraphs.append((tuple(current_lines), segment.is_literal, follows_blank))
                    current_lines = []
                follows_blank = True
            if current_lines:
                paragraphs.append((tuple(current_lines), segment.is_literal, follows_blank))
                follows_blank = False
        return tuple(paragraphs)

    def closing(self) -> str:
        """What closes the comment on its last text line, such as a docstring's quotes."""
        return self.layout.closing(self.lines)

    def render(self) -> str:
        return '\n'.join(line.render() for line in self.lines)

    def as_edit(self) -> TextEdit:
        return TextEdit(self.range, self.render())


# A line the author filled with several short sentences, each whole, reads as well as one sentence a line,
# so it stays while it fits.
def _shared_line(lines: tuple[str, ...], sentences: tuple[Sentence, ...]) -> str | None:
    start = 0
    for line in lines:
        if start == sentences[0].offset:
            end = start + len(line)
            ending_here = [sentence for sentence in sentences[1:] if sentence.end == end]
            return line if ending_here and sentences[0].end < end else None
        start += len(line) + 1
    return None


# The lines a sentence already occupies, when it has them to itself.
def _given_lines(lines: tuple[str, ...], sentence: Sentence) -> tuple[str, ...] | None:
    covering: list[str] = []
    start = 0
    for line in lines:
        end = start + len(line)
        if start < sentence.end and end > sentence.offset:
            if not covering and start != sentence.offset:
                return None
            covering.append(line)
            if end == sentence.end:
                return tuple(covering)
            if end > sentence.end:
                return None
        start = end + 1
    return None


def _keeps_given(
    given_lines: tuple[str, ...], best_lines: tuple[str, ...], budgets: tuple[int, int], stub_floor: int
) -> bool:
    # A colon ending a line in mid sentence is a rewrite finding, so its layout waits for that rewrite.
    if _breaks_at_a_colon(given_lines):
        return _fits(given_lines, budgets)
    return (
        len(given_lines) == len(best_lines)
        and _is_legal(given_lines, budgets, stub_floor)
        and break_cost(given_lines) <= break_cost(best_lines)
    )


def _breaks_at_a_colon(lines: tuple[str, ...]) -> bool:
    return any(line.endswith(':') for line in lines[:-1])


def _fits(lines: tuple[str, ...], budgets: tuple[int, int]) -> bool:
    first_budget, body_budget = budgets
    return all(len(line) <= (first_budget if index == 0 else body_budget) for index, line in enumerate(lines))


def _is_legal(lines: tuple[str, ...], budgets: tuple[int, int], stub_floor: int) -> bool:
    if not _fits(lines, budgets):
        return False
    if len(lines) == 1:
        return True
    if _strands_stub(lines, stub_floor):
        return False
    breaks = set(comma_breaks(' '.join(lines)))
    line_ends = itertools.accumulate(len(line) + 1 for line in lines[:-1])
    return all(line_end - 1 in breaks for line_end in line_ends)


def _strands_stub(lines: tuple[str, ...], stub_floor: int) -> bool:
    return len(lines) > 1 and min(map(len, lines)) < stub_floor
