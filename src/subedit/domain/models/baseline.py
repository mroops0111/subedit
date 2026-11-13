import dataclasses
import difflib

from .position import SourceRange


@dataclasses.dataclass(frozen=True, slots=True)
class Baseline:
    """The text a document is compared with, so a check reads only the prose that differs from it."""

    text: str

    def changed_ranges(self, text: str) -> tuple[SourceRange, ...]:
        """The lines of text that differ from the baseline, as byte ranges.

        A removed line leaves no line of its own, so the lines on either side of it count as changed.
        """
        old_lines = self.text.splitlines(keepends=True)
        new_lines = text.splitlines(keepends=True)
        changed_lines: set[int] = set()
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
        for tag, _, _, start, end in matcher.get_opcodes():
            if tag == 'equal':
                continue
            if tag == 'delete':
                changed_lines.update(index for index in (start - 1, start) if 0 <= index < len(new_lines))
            else:
                changed_lines.update(range(start, end))
        offsets = [0]
        for line in new_lines:
            offsets.append(offsets[-1] + len(line.encode('utf-8')))
        return tuple(SourceRange(offsets[index], offsets[index + 1]) for index in sorted(changed_lines))
