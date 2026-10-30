import pytest
from factories import document, edit

from subedit.domain import apply_edits
from subedit.domain.models.text import source_lines


def test_no_edits_returns_the_original() -> None:
    assert apply_edits('unchanged', ()) == 'unchanged'


def test_edits_apply_back_to_front_so_offsets_stay_valid() -> None:
    text = 'alpha beta gamma'
    result = apply_edits(text, (edit(0, 5, 'FIRST'), edit(11, 16, 'LAST')))
    assert result == 'FIRST beta LAST'


def test_edits_are_order_independent() -> None:
    text = 'alpha beta gamma'
    forward = apply_edits(text, (edit(0, 5, 'X'), edit(11, 16, 'Y')))
    backward = apply_edits(text, (edit(11, 16, 'Y'), edit(0, 5, 'X')))
    assert forward == backward == 'X beta Y'


def test_insertion_and_deletion() -> None:
    assert apply_edits('ac', (edit(1, 1, 'b'),)) == 'abc'
    assert apply_edits('abc', (edit(1, 2, ''),)) == 'ac'


def test_edits_respect_byte_offsets_on_multibyte_text() -> None:
    text = '€✓ old ✓€'
    start = len('€✓ '.encode())
    end = start + len(b'old')
    assert apply_edits(text, (edit(start, end, 'new'),)) == '€✓ new ✓€'


def test_overlapping_edits_are_rejected() -> None:
    with pytest.raises(ValueError, match='Overlapping edits'):
        apply_edits('alpha beta', (edit(0, 5, 'X'), edit(3, 8, 'Y')))


def test_adjacent_edits_are_allowed() -> None:
    assert apply_edits('abcd', (edit(0, 2, 'X'), edit(2, 4, 'Y'))) == 'XY'


def test_document_maps_positions_and_bumps_version_on_change() -> None:
    subject = document('const x = 1\n', 'typescript')
    assert subject.positions.line_count == 2
    assert subject.version == 0

    updated = subject.with_text('const x = 2\n')
    assert updated.version == 1
    assert updated.positions.line_text(0) == 'const x = 2'
    assert subject.text == 'const x = 1\n'


def test_document_accepts_an_explicit_version() -> None:
    subject = document('a', 'typescript')
    assert subject.with_text('b', version=42).version == 42


@pytest.mark.parametrize('text', ['', 'a', 'a\n', 'a\nb', 'a\n\nb\n', 'log\x1erecord\nnext\x0cpage\n'])
def test_source_lines_split_only_at_newlines(text: str) -> None:
    lines = source_lines(text)
    assert ''.join(lines) == text
    assert len(lines) == text.count('\n') + (not text.endswith('\n') and bool(text))
