import dataclasses

from .line_layout import LineLayout, PrefixedLine


class QuotedDocLayout(LineLayout):
    """A docstring, whose text runs on from its opening quotes with no prefix on the lines after."""

    summary_convention = 'PEP 257'
    parts_every_paragraph = True

    def text_budget(self, lines: tuple[PrefixedLine, ...], width: int, *, first_line: bool) -> int:
        opening = lines[0]
        return max(20, width - (opening.prefix_width if first_line else len(opening.indent)))

    def closing(self, lines: tuple[PrefixedLine, ...]) -> str:
        return lines[-1].suffix or lines[0].delimiter.strip()

    def rebuild(self, lines: tuple[PrefixedLine, ...], texts: tuple[str, ...], width: int) -> tuple[PrefixedLine, ...]:
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
class FramedDocLayout(LineLayout):
    """A doc block such as JSDoc, framed by an opening line, a prefix on each text line, and a closing line."""

    parts_every_paragraph = True
    opening: str
    prefix: str
    closing_line: str

    def text_budget(self, lines: tuple[PrefixedLine, ...], width: int, *, first_line: bool) -> int:
        return max(20, width - len(lines[0].indent) - len(self.prefix))

    def rebuild(self, lines: tuple[PrefixedLine, ...], texts: tuple[str, ...], width: int) -> tuple[PrefixedLine, ...]:
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


QUOTED_DOC_LAYOUT = QuotedDocLayout()
