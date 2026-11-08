import abc
import dataclasses
import typing

from .line_layout import LineLayout, PrefixedLine
from .position import SourceRange
from .prose import LIST_MARKER, Prose, ProseMarkup
from .prose_unit import ProseLine, ProseUnit
from .reflow import (
    BreakPolicy,
    break_cost,
    is_legal,
    keeps_given,
    line_shared_by,
    occupied_lines,
    reflow_sentence,
    strands_stub,
)
from .text import TextEdit


class LaidOutProse(ProseUnit, abc.ABC):
    """Prose set on lines of a width, which reflow lays out sentence by sentence.

    A subclass is a frozen dataclass holding these fields, and says when its text must keep the layout it has.
    """

    __slots__ = ()

    surface_name: typing.ClassVar[str] = 'Laid Out Prose'

    range: SourceRange
    lines: tuple[PrefixedLine, ...]
    layout: LineLayout
    markup: ProseMarkup

    @property
    def stays_on_its_line(self) -> bool:
        """Whether the text shares its line with something else, such as code, so it never breaks."""
        return False

    def keeps_its_layout(self, width: int) -> bool:
        """Whether reflow leaves the text as written, which it does for text that stays on its line."""
        return self.stays_on_its_line

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def longest_line(self) -> int:
        return max(line.physical_width for line in self.lines)

    @property
    def has_summary_line(self) -> bool:
        """Whether the first sentence is a one-line summary, as the style guide the layout follows asks."""
        return self.layout.summary_convention is not None

    def prose(self) -> Prose:
        filled_lines = [line for line in self.lines if line.text.strip()]
        base = min((len(line.indent) for line in filled_lines), default=0)
        rendered_lines = [
            ' ' * max(0, len(line.indent) - base) + line.text.rstrip() if line.text.strip() else ''
            for line in self.lines
        ]
        return Prose('\n'.join(rendered_lines), self.markup)

    def prose_lines(self) -> tuple[ProseLine, ...]:
        """The lines of prose, without code, a fence, or a tag section, each with its list marker set apart."""
        shown_lines = self.prose().physical_lines
        code_indexes = self.prose().code_line_indexes()
        skipped: set[int] = set(code_indexes)
        inside_tags = False
        for index, shown in enumerate(shown_lines):
            inside_tags = inside_tags or self.markup.opens_tag_section(shown)
            if inside_tags or not shown.strip() or shown.lstrip().startswith(('```', '~~~')):
                skipped.add(index)
        prose_lines: list[ProseLine] = []
        for index, line in enumerate(self.lines):
            if index in skipped:
                continue
            marker = LIST_MARKER.match(line.text)
            marker_length = marker.end() if marker else 0
            text_start = line.range.start + len((line.indent + line.delimiter).encode('utf-8'))
            text = line.text[marker_length:]
            start = text_start + len(line.text[:marker_length].encode('utf-8'))
            following = index + 1
            prose_lines.append(
                ProseLine(
                    range=SourceRange(start, start + len(text.encode('utf-8'))),
                    text=text,
                    opens_item=marker is not None,
                    ends_paragraph=following >= len(self.lines)
                    or following in skipped
                    or LIST_MARKER.match(self.lines[following].text) is not None,
                    opens_paragraph=index == 0 or index - 1 in skipped,
                )
            )
        return tuple(prose_lines)

    def editable_ranges(self) -> tuple[SourceRange, ...]:
        """Text on its own lines, the only text an outside checker may edit, since it must leave a shared line alone."""
        if self.stays_on_its_line:
            return ()
        return tuple(line.range for line in self.lines)

    def code_ranges(self) -> tuple[SourceRange, ...]:
        """Where the lines holding code sit, which a prose checker has no business reading."""
        return tuple(self.lines[index].range for index in sorted(self.prose().code_line_indexes()))

    def reflow(self, width: int, policy: BreakPolicy = BreakPolicy()) -> typing.Self:
        if self.keeps_its_layout(width):
            return self
        texts = self._reflow_into_texts(width, policy)
        # Text that ends up on one line closes there too, so the closing quotes need room beside it.
        closing_width = len(self.closing())
        if len(texts) == 1 and len(texts[0]) > self.text_budget(width, first_line=True) - closing_width:
            texts = self._reflow_into_texts(width, policy, closing_width)
        if not texts:
            return self
        # Every unit is a frozen dataclass, which the type checker cannot see through an abstract base.
        rebuilt: typing.Self = dataclasses.replace(
            typing.cast(typing.Any, self), lines=self.layout.rebuild(self.lines, texts, width)
        )
        # A sentence with no legal break may come out longer than the author wrapped it,
        # and a fix that pushes a line past the width trades one finding for another.
        if rebuilt.longest_line > max(width, self.longest_line):
            return self
        return rebuilt

    def sentences_splitting_a_list(self, width: int, policy: BreakPolicy) -> tuple[str, ...]:
        """The sentences whose layout, once reflowed, breaks beside an item of a list."""
        splitting: list[str] = []
        self._reflow_into_texts(width, policy, splitting=splitting)
        return tuple(splitting)

    def text_budget(self, width: int, *, first_line: bool) -> int:
        """The characters of text a line holds, which on the opening line also cede what opens the text."""
        return self.layout.text_budget(self.lines, width, first_line=first_line)

    # A sentence takes as few lines as fit, and the author's layout stays when it is legal.
    # A sentence whose new layout would strand a stub or still overflow needs its author,
    # so it keeps the layout they gave it rather than one its own check rejects.
    # A summary never breaks where the text's style guide keeps it to one line.
    def _reflow_into_texts(
        self, width: int, policy: BreakPolicy, reserve: int = 0, splitting: list[str] | None = None
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
            sentences = Prose(' '.join(lines)).sentences(policy.abbreviations)
            shared_until = 0
            for sentence_index, sentence in enumerate(sentences):
                if sentence.offset < shared_until:
                    continue
                if sentence_index == 1 and paragraph_index == 0 and self.has_summary_line:
                    out.append('')
                first_budget = self.text_budget(width, first_line=not out) - (reserve if not out else 0)
                is_summary = self.has_summary_line and paragraph_index == 0 and sentence_index == 0
                shared_line = None if is_summary else line_shared_by(lines, sentences[sentence_index:])
                if shared_line is not None and len(shared_line) <= first_budget:
                    out.append(shared_line)
                    shared_until = sentence.offset + len(shared_line)
                    continue
                if is_summary:
                    best_lines: tuple[str, ...] = (sentence.text,)
                else:
                    best_lines = reflow_sentence(sentence.text, body_budget, policy, first_width=first_budget)
                given_lines = occupied_lines(lines, sentence)
                budgets = (first_budget, body_budget)
                if given_lines and keeps_given(given_lines, best_lines, budgets, policy.stub_floor):
                    laid_out = given_lines
                elif is_legal(best_lines, budgets, policy.stub_floor):
                    laid_out = best_lines
                elif given_lines:
                    laid_out = given_lines
                elif strands_stub(best_lines, policy.stub_floor):
                    return ()
                else:
                    laid_out = best_lines
                if (
                    splitting is not None
                    and policy.list_item_words is not None
                    and break_cost(laid_out, policy.list_item_words)
                ):
                    splitting.append(sentence.text)
                out.extend(laid_out)
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
        """What closes the text on its last line, which that line must leave room for."""
        return self.layout.closing(self.lines)

    def render(self) -> str:
        return '\n'.join(line.render() for line in self.lines)

    def as_edit(self) -> TextEdit:
        return TextEdit(self.range, self.render())
