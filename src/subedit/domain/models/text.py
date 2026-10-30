import dataclasses
import itertools

from .position import SourceRange


@dataclasses.dataclass(frozen=True, slots=True)
class TextEdit:
    """Text that replaces a range of bytes."""

    range: SourceRange
    new_text: str


def source_lines(text: str) -> list[str]:
    """The lines a source file holds, each with its newline, split where a newline falls and nowhere else.

    str.splitlines also splits at characters such as a form feed or a record separator,
    which leave a line's number out of step with what an editor, patch, and PositionMap count.
    """
    pieces = text.split('\n')
    lines = [piece + '\n' for piece in pieces[:-1]]
    if pieces[-1]:
        lines.append(pieces[-1])
    return lines


def apply_edits(text: str, edits: tuple[TextEdit, ...]) -> str:
    """The text with every edit applied from the last to the first, so no edit moves the offsets of another."""
    if not edits:
        return text
    sorted_edits = sorted(edits, key=lambda edit: (edit.range.start, edit.range.end))
    for earlier_edit, later_edit in itertools.pairwise(sorted_edits):
        if earlier_edit.range.overlaps(later_edit.range):
            raise ValueError(f'Overlapping edits at bytes {earlier_edit.range.start} and {later_edit.range.start}')
    buffer = bytearray(text.encode('utf-8'))
    for edit in reversed(sorted_edits):
        buffer[edit.range.start : edit.range.end] = edit.new_text.encode('utf-8')
    return buffer.decode('utf-8')
