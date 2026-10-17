import dataclasses
import enum
import itertools

from .position import SourceRange
from .prose import Prose, Sentence, break_cost, comma_breaks, reflow_sentence
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


@dataclasses.dataclass(frozen=True, slots=True)
class CommentLine:
    range: SourceRange
    indent: str
    delimiter: str
    text: str
    suffix: str = ''

    @property
    def physical_width(self) -> int:
        return len(self.indent) + len(self.delimiter) + len(self.text) + len(self.suffix)

    @property
    def prefix_width(self) -> int:
        return len(self.indent) + len(self.delimiter)

    def render(self) -> str:
        if not self.text and not self.suffix:
            return (self.indent + self.delimiter).rstrip()
        return self.indent + self.delimiter + self.text + self.suffix


@dataclasses.dataclass(frozen=True, slots=True)
class DocFrame:
    """The frame a doc comment such as JSDoc wraps its text in, with an opening, a prefix per line, and a closing.

    A docstring has none, since its text runs on from the opening quotes and needs no prefix.
    """

    opening: str
    prefix: str
    closing: str

    def one_line(self) -> tuple[str, str]:
        """The delimiter and suffix around text that opens and closes on one line."""
        return f'{self.opening} ', f' {self.closing.strip()}'


@dataclasses.dataclass(frozen=True, slots=True)
class CommentGroup:
    range: SourceRange
    lines: tuple[CommentLine, ...]
    form: CommentForm
    placement: CommentPlacement
    attachment: SymbolRef | None = None
    frame: DocFrame | None = None

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
        """Whether the first sentence is a one-line summary, as PEP 257 asks of a docstring."""
        return self.form is CommentForm.DOC and self.frame is None

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
        return Prose('\n'.join(rendered_lines))

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
        closing_width = len(self.closing_quotes())
        if len(texts) == 1 and len(texts[0]) > self.text_budget(width, first_line=True) - closing_width:
            texts = self._reflow_into_texts(width, stub_floor, closing_width)
        if not texts:
            return self
        return self._rebuild_lines(texts)

    def sentences_held_by_a_list(self, width: int, stub_floor: int = 0) -> tuple[str, ...]:
        """The sentences reflow leaves as the author broke them, since every legal break would split a list."""
        held: list[str] = []
        self._reflow_into_texts(width, stub_floor, held=held)
        return tuple(held)

    def text_budget(self, width: int, *, first_line: bool) -> int:
        """The characters of text a line holds, which on a docstring's opening line also cede the quotes."""
        opening = self.lines[0]
        if self.frame is not None:
            return max(20, width - len(opening.indent) - len(self.frame.prefix))
        quoted = first_line or self.form is not CommentForm.DOC
        return max(20, width - (opening.prefix_width if quoted else len(opening.indent)))

    # A sentence takes as few lines as fit, and the author's layout stays when it breaks no worse than the best one.
    # A sentence whose new layout would strand a stub, split a list, or still overflow needs its author,
    # so it keeps the layout they gave it rather than one its own check rejects.
    # A docstring's summary never breaks, since PEP 257 keeps it to one line.
    def _reflow_into_texts(
        self, width: int, stub_floor: int, reserve: int = 0, held: list[str] | None = None
    ) -> tuple[str, ...]:
        body_budget = self.text_budget(width, first_line=False)
        out: list[str] = []
        for paragraph_index, (paragraph, is_literal, follows_blank) in enumerate(self._split_into_paragraphs()):
            # reStructuredText reads a list as part of the paragraph above it unless a blank line parts them,
            # while a line comment's list may sit right under the line that introduces it.
            if out and (follows_blank or self.form is CommentForm.DOC):
                out.append('')
            if is_literal:
                out.extend(paragraph)
                continue
            lines = tuple(line.strip() for line in paragraph if line.strip())
            for sentence_index, sentence in enumerate(Prose(' '.join(lines)).sentences()):
                if sentence_index == 1 and paragraph_index == 0 and self.has_summary_line:
                    out.append('')
                first_budget = self.text_budget(width, first_line=not out) - (reserve if not out else 0)
                if self.has_summary_line and paragraph_index == 0 and sentence_index == 0:
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

    def _rebuild_lines(self, texts: tuple[str, ...]) -> 'CommentGroup':
        if self.form is not CommentForm.DOC:
            return self.with_texts(texts)
        if self.frame is not None:
            return self._rebuild_framed(texts, self.frame)
        opening, closing = self.lines[0], self.lines[-1]
        closes_alone = len(self.lines) > 1 and not closing.text.strip()
        body = [dataclasses.replace(opening, delimiter='', suffix='', text=text, range=opening.range) for text in texts]
        body[0] = dataclasses.replace(body[0], delimiter=opening.delimiter)
        # Text that fits one line closes on that line, as ruff and black format it.
        if len(texts) > 1:
            body.append(
                dataclasses.replace(closing, delimiter=closing.delimiter or opening.delimiter, text='', suffix='')
            )
            if not closes_alone:
                body[-1] = dataclasses.replace(body[-1], delimiter=opening.delimiter.strip())
        else:
            body[0] = dataclasses.replace(body[0], suffix=self.closing_quotes())
        return dataclasses.replace(self, lines=tuple(body))

    # A block that opened and closed on one line stays there while its text fits.
    def _rebuild_framed(self, texts: tuple[str, ...], frame: DocFrame) -> 'CommentGroup':
        opening = self.lines[0]
        if len(texts) == 1 and self.line_count == 1:
            delimiter, suffix = frame.one_line()
            return dataclasses.replace(
                self, lines=(dataclasses.replace(opening, delimiter=delimiter, text=texts[0], suffix=suffix),)
            )
        bare = dataclasses.replace(opening, text='', suffix='')
        body = [dataclasses.replace(bare, delimiter=frame.opening)]
        body.extend(dataclasses.replace(bare, delimiter=frame.prefix, text=text) for text in texts)
        body.append(dataclasses.replace(bare, delimiter=frame.closing))
        return dataclasses.replace(self, lines=tuple(body))

    def closing_quotes(self) -> str:
        if self.form is not CommentForm.DOC or self.frame is not None:
            return ''
        return self.lines[-1].suffix or self.lines[0].delimiter.strip()

    def with_texts(self, texts: tuple[str, ...]) -> 'CommentGroup':
        if not texts:
            raise ValueError('A comment block needs at least one line')
        # A blank line's delimiter drops its space, so a text moved onto it takes the spacing of a filled one.
        template = next((line for line in self.lines if line.text), self.lines[0])
        rebuilt = tuple(
            dataclasses.replace(
                self.lines[index] if index < len(self.lines) else template,
                delimiter=template.delimiter if text else template.delimiter.rstrip(),
                text=text,
            )
            for index, text in enumerate(texts)
        )
        return dataclasses.replace(self, lines=rebuilt)

    def render(self) -> str:
        return '\n'.join(line.render() for line in self.lines)

    def as_edit(self) -> TextEdit:
        return TextEdit(self.range, self.render())


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
