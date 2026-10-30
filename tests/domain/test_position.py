import pytest

from subedit.domain import Encoding, Position, PositionMap, SourceRange


ONE_BYTE = 'const x = 1\nconst y = 2\n'
TWO_BYTE = 'cafe\u0301 vs café\nsecond naïve line\n'
THREE_BYTE = 'a three byte run €€\nsecond line ✓✓\n'
FOUR_BYTE = 'tail 🐍 head\nsecond 🎯 line\n'
JOINED_GRAPHEME = 'family 👨\u200d👩\u200d👧 done\n'
MIXED_WIDTH = '// note é € 🐍 together\n// second\n'
CRLF_LINES = 'alpha\r\nbeta\r\n'
NO_FINAL_NEWLINE = 'alpha\nbeta'
EMPTY = ''

ALL_TEXTS = [
    ONE_BYTE,
    TWO_BYTE,
    THREE_BYTE,
    FOUR_BYTE,
    JOINED_GRAPHEME,
    MIXED_WIDTH,
    CRLF_LINES,
    NO_FINAL_NEWLINE,
    EMPTY,
]


@pytest.mark.parametrize('text', ALL_TEXTS)
@pytest.mark.parametrize('encoding', list(Encoding))
def test_offset_position_round_trip(text: str, encoding: Encoding) -> None:
    mapper = PositionMap(text)
    data = text.encode('utf-8')
    for offset in range(len(data) + 1):
        if offset < len(data) and 0x80 <= data[offset] < 0xC0:
            continue
        if data[offset - 1 : offset] == b'\r' or data[offset : offset + 1] == b'\r':
            continue
        assert mapper.to_offset(mapper.to_position(offset, encoding), encoding) == offset


def test_offset_inside_a_line_terminator_clamps_to_the_content_end() -> None:
    mapper = PositionMap('alpha\r\nbeta')
    carriage_return = len(b'alpha')
    line_feed = carriage_return + 1
    assert mapper.to_position(carriage_return).character == 5
    assert mapper.to_position(line_feed).character == 5


@pytest.mark.parametrize('text', ALL_TEXTS)
def test_line_text_reconstructs_the_document(text: str) -> None:
    mapper = PositionMap(text)
    joined = '\n'.join(mapper.line_text(line) for line in range(mapper.line_count))
    assert joined.replace('\r', '') == text.replace('\r', '').removesuffix('\n') + ('\n' if text.endswith('\n') else '')


def test_utf16_counts_surrogate_pairs_as_two() -> None:
    mapper = PositionMap('a🐍b')
    assert mapper.to_position(len('a🐍'.encode()), Encoding.UTF16).character == 3
    assert mapper.to_position(len('a🐍'.encode()), Encoding.UTF32).character == 2
    assert mapper.to_position(len('a🐍'.encode()), Encoding.UTF8).character == 5


def test_multibyte_below_the_bmp_costs_one_unit_in_both_utf16_and_utf32() -> None:
    mapper = PositionMap('€✓')
    offset = len('€✓'.encode())
    assert mapper.to_position(offset, Encoding.UTF16).character == 2
    assert mapper.to_position(offset, Encoding.UTF32).character == 2
    assert mapper.to_position(offset, Encoding.UTF8).character == 6


def test_crlf_is_excluded_from_line_range() -> None:
    mapper = PositionMap(CRLF_LINES)
    assert mapper.line_text(0) == 'alpha'
    assert mapper.line_text(1) == 'beta'


def test_line_starts_track_every_newline() -> None:
    mapper = PositionMap(ONE_BYTE)
    assert mapper.line_count == 3
    assert mapper.line_text(2) == ''


def test_out_of_range_offset_is_rejected() -> None:
    mapper = PositionMap(ONE_BYTE)
    with pytest.raises(ValueError, match='out of range'):
        mapper.to_position(len(ONE_BYTE.encode()) + 1)


def test_out_of_range_line_is_rejected() -> None:
    mapper = PositionMap(ONE_BYTE)
    with pytest.raises(ValueError, match='out of range'):
        mapper.line_range(99)


def test_character_past_line_end_clamps_to_line_end() -> None:
    mapper = PositionMap(ONE_BYTE)
    assert mapper.to_offset(Position(0, 999)) == mapper.line_range(0).end


def test_negative_position_is_rejected() -> None:
    with pytest.raises(ValueError, match='non negative'):
        Position(-1, 0)


def test_inverted_range_is_rejected() -> None:
    with pytest.raises(ValueError, match='precedes start'):
        SourceRange(5, 2)


def test_negative_range_start_is_rejected() -> None:
    with pytest.raises(ValueError, match='non negative'):
        SourceRange(-1, 3)


@pytest.mark.parametrize(
    ('left', 'right', 'expected'),
    [
        (SourceRange(0, 5), SourceRange(3, 8), True),
        (SourceRange(0, 5), SourceRange(5, 8), False),
        (SourceRange(0, 5), SourceRange(1, 2), True),
        (SourceRange(3, 3), SourceRange(0, 5), True),
        (SourceRange(0, 5), SourceRange(0, 0), False),
        (SourceRange(0, 5), SourceRange(5, 5), False),
        (SourceRange(3, 3), SourceRange(3, 3), False),
    ],
)
def test_range_overlap(left: SourceRange, right: SourceRange, expected: bool) -> None:
    assert left.overlaps(right) is expected
    assert right.overlaps(left) is expected


def test_range_containment_and_measures() -> None:
    outer = SourceRange(0, 10)
    assert outer.contains(SourceRange(2, 8))
    assert not outer.contains(SourceRange(2, 11))
    assert outer.length == 10
    assert SourceRange(4, 4).is_empty
