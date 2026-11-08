import abc
import dataclasses

from .position import SourceRange


@dataclasses.dataclass(frozen=True, slots=True)
class PrefixedLine:
    """A source line as its indent, a delimiter that opens it, which may be empty, its text, and what closes it."""

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


class LineLayout(abc.ABC):
    """How text is set on lines, which the syntax around it decides and reflow follows."""

    # The style guide that keeps the first sentence to one line, as a summary indexing tools read alone.
    summary_convention: str | None = None
    # Some markup reads a list as part of the paragraph above it unless a blank line parts them,
    # while elsewhere a list may sit right under the line that introduces it.
    parts_every_paragraph = False

    @abc.abstractmethod
    def text_budget(self, lines: tuple[PrefixedLine, ...], width: int, *, first_line: bool) -> int:
        """The characters of text one line holds once the indent and the delimiter take their share."""

    @abc.abstractmethod
    def rebuild(self, lines: tuple[PrefixedLine, ...], texts: tuple[str, ...], width: int) -> tuple[PrefixedLine, ...]:
        """Set the texts on lines of this syntax, in place of the lines given."""

    def closing(self, lines: tuple[PrefixedLine, ...]) -> str:
        """What closes the text on its last line, which that line must leave room for."""
        return ''


class LinePrefixLayout(LineLayout):
    """Text whose every line opens with the same delimiter, which may be empty."""

    def text_budget(self, lines: tuple[PrefixedLine, ...], width: int, *, first_line: bool) -> int:
        return max(20, width - lines[0].prefix_width)

    def rebuild(self, lines: tuple[PrefixedLine, ...], texts: tuple[str, ...], width: int) -> tuple[PrefixedLine, ...]:
        if not texts:
            raise ValueError('Text needs at least one line')
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


LINE_LAYOUT = LinePrefixLayout()
