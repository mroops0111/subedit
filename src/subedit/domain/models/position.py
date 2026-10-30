import bisect
import dataclasses
import enum


class Encoding(enum.Enum):
    UTF8 = 'utf-8'
    UTF16 = 'utf-16'
    UTF32 = 'utf-32'


@dataclasses.dataclass(frozen=True, slots=True)
class Position:
    line: int
    character: int

    def __post_init__(self) -> None:
        if self.line < 0 or self.character < 0:
            raise ValueError(f'Position must be non negative, got line {self.line} character {self.character}')


@dataclasses.dataclass(frozen=True, slots=True)
class SourceRange:
    """A stretch of a document, from a start byte up to an end byte, in UTF-8."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f'Range start must be non negative, got {self.start}')
        if self.end < self.start:
            raise ValueError(f'Range end {self.end} precedes start {self.start}')

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def is_empty(self) -> bool:
        return self.start == self.end

    def overlaps(self, other: 'SourceRange') -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, other: 'SourceRange') -> bool:
        return self.start <= other.start and other.end <= self.end


class PositionMap:
    """Converts byte offsets to the line and character positions an editor counts, in any encoding."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._encoded_text = text.encode('utf-8')
        starts = [0]
        for index, byte in enumerate(self._encoded_text):
            if byte == 0x0A:
                starts.append(index + 1)
        self._line_starts = starts

    @property
    def line_count(self) -> int:
        return len(self._line_starts)

    def line_range(self, line: int) -> SourceRange:
        self._require_line(line)
        start = self._line_starts[line]
        if line + 1 < len(self._line_starts):
            end = self._line_starts[line + 1] - 1
            if end > start and self._encoded_text[end - 1] == 0x0D:
                end -= 1
        else:
            end = len(self._encoded_text)
        return SourceRange(start, end)

    def line_text(self, line: int) -> str:
        span = self.line_range(line)
        return self._encoded_text[span.start : span.end].decode('utf-8')

    def to_position(self, offset: int, encoding: Encoding = Encoding.UTF16) -> Position:
        self._require_offset(offset)
        line = bisect.bisect_right(self._line_starts, offset) - 1
        span = self.line_range(line)
        prefix = self._encoded_text[span.start : min(offset, span.end)].decode('utf-8')
        return Position(line, self._measure(prefix, encoding))

    def to_offset(self, position: Position, encoding: Encoding = Encoding.UTF16) -> int:
        self._require_line(position.line)
        span = self.line_range(position.line)
        text = self._encoded_text[span.start : span.end].decode('utf-8')
        consumed = 0
        for index, character in enumerate(text):
            if consumed >= position.character:
                return span.start + len(text[:index].encode('utf-8'))
            consumed += self._measure(character, encoding)
        return span.end

    def _measure(self, text: str, encoding: Encoding) -> int:
        if encoding is Encoding.UTF8:
            return len(text.encode('utf-8'))
        if encoding is Encoding.UTF32:
            return len(text)
        return sum(2 if character > '￿' else 1 for character in text)

    def _require_line(self, line: int) -> None:
        if not 0 <= line < len(self._line_starts):
            raise ValueError(f'Line {line} out of range, document has {len(self._line_starts)} lines')

    def _require_offset(self, offset: int) -> None:
        if not 0 <= offset <= len(self._encoded_text):
            raise ValueError(f'Offset {offset} out of range, document has {len(self._encoded_text)} bytes')
