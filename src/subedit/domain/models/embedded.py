import dataclasses

from .diagnostic import Diagnostic, Fix
from .position import SourceRange
from .text import TextEdit


@dataclasses.dataclass(frozen=True, slots=True)
class EmbeddedDocument:
    """A document held inside another, such as a code block in Markdown, and where each of its lines sits in its host.

    A host may set every line apart with a prefix, such as a list item's indent or a block quote's marker,
    so a finding maps back line by line, and an edit that spans lines puts each prefix back.
    """

    language_name: str
    text: str
    # Where each line of the text starts in the host, in bytes, past the prefix the host gives it.
    host_starts: tuple[int, ...]
    prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.host_starts) != len(self._line_starts()) or len(self.prefixes) != len(self.host_starts):
            raise ValueError('An embedded document needs one host start and one prefix per line')

    def host_range(self, inner: SourceRange) -> SourceRange:
        """The range in the host that holds the given range of the embedded text."""
        return SourceRange(self._host_offset(inner.start), self._host_offset(inner.end))

    def host_diagnostic(self, diagnostic: Diagnostic) -> Diagnostic:
        """The finding as the host reads it, with its range and every edit it offers moved into the host."""
        fix = diagnostic.fix
        if fix is not None and fix.edits:
            fix = Fix(fix.kind, tuple(self._host_edit(edit) for edit in fix.edits))
        return dataclasses.replace(diagnostic, range=self.host_range(diagnostic.range), fix=fix)

    def _host_edit(self, edit: TextEdit) -> TextEdit:
        prefix = self.prefixes[self._line_of(edit.range.start)]
        lines = edit.new_text.split('\n')
        # A blank line takes the prefix without its trailing space, so no line ends in whitespace.
        rebuilt = lines[0] + ''.join(f'\n{prefix if line else prefix.rstrip()}{line}' for line in lines[1:])
        return TextEdit(self.host_range(edit.range), rebuilt)

    def _host_offset(self, offset: int) -> int:
        line = self._line_of(offset)
        return self.host_starts[line] + offset - self._line_starts()[line]

    def _line_of(self, offset: int) -> int:
        starts = self._line_starts()
        return max(index for index, start in enumerate(starts) if start <= offset)

    def _line_starts(self) -> tuple[int, ...]:
        encoded = self.text.encode('utf-8')
        starts = [0] + [index + 1 for index, byte in enumerate(encoded) if byte == 0x0A]
        # A text ending in a newline holds no line after it.
        if starts[-1] == len(encoded) and len(starts) > 1:
            starts.pop()
        return tuple(starts)
