import re

from ...domain.models.comment_layout import CommentLine
from ...domain.models.commit_message import CommitBody, CommitSubject
from ...domain.models.document import Document
from ...domain.models.file_type import FileType
from ...domain.models.position import SourceRange
from ...domain.models.prose_unit import ProseUnit
from ...domain.ports.source_parser import ParsedDocument, SourceParser


# git writes a message to one of these files for the editor, and a commit-msg hook gets the same path.
COMMIT_MESSAGE = FileType(
    language_id='git-commit',
    extensions=frozenset(),
    canonical_extension='.md',
    file_names=frozenset({'COMMIT_EDITMSG', 'MERGE_MSG', 'SQUASH_MSG', 'TAG_EDITMSG'}),
    line_width=72,
)

# A Conventional Commits type with its scope and breaking mark, or a subsystem as the Linux kernel writes it.
_PREFIX = re.compile(r'^[\w./-]+(?:\([^)]*\))?!?: ')
# git drops the lines its commentChar opens, which also opens the scissors line that commit -v adds,
# and it writes them after the message, so the first one ends it.
_COMMENT = '#'
# A trailer is a token and a value, as git interpret-trailers reads it, or a keyword GitHub closes an issue with.
_TRAILER = re.compile(r'^[A-Za-z0-9][\w-]*: \S|^(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?) #\d+\s*$', re.IGNORECASE)


class CommitMessageParser(SourceParser[ProseUnit]):
    """Reads a commit message as its subject and its body, leaving the trailers and git's comments unread."""

    @property
    def file_types(self) -> tuple[FileType, ...]:
        return (COMMIT_MESSAGE,)

    def read(self, document: Document) -> ParsedDocument[ProseUnit]:
        lines = _Lines(document.text)
        message_end = next(
            (index for index, text in enumerate(lines.texts) if text.startswith(_COMMENT)), len(lines.texts)
        )
        subject_index = next((index for index in range(message_end) if lines.texts[index].strip()), None)
        if subject_index is None:
            return ParsedDocument(skipped=lines.span_from(message_end))
        units: list[ProseUnit] = [self._subject(lines, subject_index, message_end)]
        body_start = subject_index + 1
        while body_start < message_end and not lines.texts[body_start].strip():
            body_start += 1
        body_end = _trailers_start(lines.texts, body_start, message_end)
        while body_end > body_start and not lines.texts[body_end - 1].strip():
            body_end -= 1
        if body_start < body_end:
            units.append(
                CommitBody(
                    range=SourceRange(lines.ranges[body_start].start, lines.ranges[body_end - 1].end),
                    lines=tuple(
                        CommentLine(range=lines.ranges[index], indent='', delimiter='', text=lines.texts[index])
                        for index in range(body_start, body_end)
                    ),
                )
            )
        return ParsedDocument(units=tuple(units), skipped=lines.span_from(body_end, skip_blank=True))

    def _subject(self, lines: '_Lines', index: int, message_end: int) -> CommitSubject:
        text = lines.texts[index]
        prefix = _PREFIX.match(text)
        following = index + 1
        return CommitSubject(
            range=lines.ranges[index],
            prefix=prefix.group() if prefix else '',
            description=text[prefix.end() :] if prefix else text,
            runs_into_body=following < message_end and bool(lines.texts[following].strip()),
        )


class _Lines:
    """The lines of a message without their line breaks, each with its byte range."""

    def __init__(self, text: str) -> None:
        self.texts = text.split('\n')
        if self.texts and self.texts[-1] == '':
            self.texts.pop()
        self.ranges: list[SourceRange] = []
        offset = 0
        for line in self.texts:
            width = len(line.encode('utf-8'))
            self.ranges.append(SourceRange(offset, offset + width))
            offset += width + 1

    def span_from(self, start: int, *, skip_blank: bool = False) -> tuple[SourceRange, ...]:
        """The ranges of the lines from start on, which no prose checker reads."""
        return tuple(
            self.ranges[index]
            for index in range(start, len(self.texts))
            if not (skip_blank and not self.texts[index].strip()) and self.ranges[index].end > self.ranges[index].start
        )


# The trailers are the last paragraph, when every line of it is one, so a body ends where they begin.
def _trailers_start(texts: list[str], start: int, end: int) -> int:
    last = end
    while last > start and not texts[last - 1].strip():
        last -= 1
    first = last
    while first > start and texts[first - 1].strip():
        first -= 1
    paragraph = texts[first:last]
    if paragraph and all(_TRAILER.match(line) for line in paragraph):
        return first
    return end
