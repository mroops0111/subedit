import abc
import dataclasses

from .position import SourceRange


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


class CommentLayout(abc.ABC):
    """How a comment sets its text on lines, which each language's comment syntax decides and reflow follows."""

    # PEP 257 keeps a docstring's first sentence to one line, as a summary indexing tools read alone.
    has_summary_line = False
    # reStructuredText and Markdown read a list as part of the paragraph above it unless a blank line parts them,
    # while a line comment's list may sit right under the line that introduces it.
    parts_every_paragraph = False

    @abc.abstractmethod
    def text_budget(self, lines: tuple[CommentLine, ...], width: int, *, first_line: bool) -> int:
        """The characters of text one line holds once the indent and the comment syntax take their share."""

    @abc.abstractmethod
    def rebuild(self, lines: tuple[CommentLine, ...], texts: tuple[str, ...], width: int) -> tuple[CommentLine, ...]:
        """Set the texts on lines of this syntax, in place of the lines given."""

    def closing(self, lines: tuple[CommentLine, ...]) -> str:
        """What closes the comment on its last text line, which that line must leave room for."""
        return ''


class LinePrefixLayout(CommentLayout):
    """A comment whose every line opens with the same delimiter, such as # or //."""

    def text_budget(self, lines: tuple[CommentLine, ...], width: int, *, first_line: bool) -> int:
        return max(20, width - lines[0].prefix_width)

    def rebuild(self, lines: tuple[CommentLine, ...], texts: tuple[str, ...], width: int) -> tuple[CommentLine, ...]:
        if not texts:
            raise ValueError('A comment block needs at least one line')
        # A blank line's delimiter drops its space, so a text moved onto it takes the spacing of a filled one.
        template = next((line for line in lines if line.text), lines[0])
        return tuple(
            dataclasses.replace(
                lines[index] if index < len(lines) else template,
                delimiter=template.delimiter if text else template.delimiter.rstrip(),
                text=text,
            )
            for index, text in enumerate(texts)
        )


class QuotedDocLayout(CommentLayout):
    """A docstring, whose text runs on from its opening quotes with no prefix on the lines after."""

    has_summary_line = True
    parts_every_paragraph = True

    def text_budget(self, lines: tuple[CommentLine, ...], width: int, *, first_line: bool) -> int:
        opening = lines[0]
        return max(20, width - (opening.prefix_width if first_line else len(opening.indent)))

    def closing(self, lines: tuple[CommentLine, ...]) -> str:
        return lines[-1].suffix or lines[0].delimiter.strip()

    def rebuild(self, lines: tuple[CommentLine, ...], texts: tuple[str, ...], width: int) -> tuple[CommentLine, ...]:
        opening, closing = lines[0], lines[-1]
        closes_alone = len(lines) > 1 and not closing.text.strip()
        body = [dataclasses.replace(opening, delimiter='', suffix='', text=text) for text in texts]
        body[0] = dataclasses.replace(body[0], delimiter=opening.delimiter)
        # Text that fits one line closes on that line, as ruff and black format it.
        if len(texts) == 1:
            body[0] = dataclasses.replace(body[0], suffix=self.closing(lines))
            return tuple(body)
        body.append(dataclasses.replace(closing, delimiter=closing.delimiter or opening.delimiter, text='', suffix=''))
        if not closes_alone:
            body[-1] = dataclasses.replace(body[-1], delimiter=opening.delimiter.strip())
        return tuple(body)


@dataclasses.dataclass(frozen=True, slots=True)
class FramedDocLayout(CommentLayout):
    """A doc block such as JSDoc, framed by an opening line, a prefix on each text line, and a closing line."""

    parts_every_paragraph = True
    opening: str
    prefix: str
    closing_line: str

    def text_budget(self, lines: tuple[CommentLine, ...], width: int, *, first_line: bool) -> int:
        return max(20, width - len(lines[0].indent) - len(self.prefix))

    def rebuild(self, lines: tuple[CommentLine, ...], texts: tuple[str, ...], width: int) -> tuple[CommentLine, ...]:
        """Open the frame, unless the block sat on one line and its text, framed on both sides, still fits there."""
        opening = lines[0]
        if len(texts) == 1 and len(lines) == 1:
            one_line = dataclasses.replace(
                opening, delimiter=f'{self.opening} ', text=texts[0], suffix=f' {self.closing_line.strip()}'
            )
            if one_line.physical_width <= width:
                return (one_line,)
        bare = dataclasses.replace(opening, text='', suffix='')
        return (
            dataclasses.replace(bare, delimiter=self.opening),
            *(dataclasses.replace(bare, delimiter=self.prefix, text=text) for text in texts),
            dataclasses.replace(bare, delimiter=self.closing_line),
        )


LINE_LAYOUT = LinePrefixLayout()
QUOTED_DOC_LAYOUT = QuotedDocLayout()
