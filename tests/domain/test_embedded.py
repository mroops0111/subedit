import pytest
from factories import edit

from subedit.domain import Diagnostic, EmbeddedDocument, Fix, SourceRange, TextEdit


QUOTED = EmbeddedDocument(language_name='py', text='# one\n# two\n', host_starts=(12, 20), prefixes=('> ', '> '))


def moved_edits(finding: Diagnostic) -> tuple[TextEdit, ...]:
    fix = QUOTED.host_diagnostic(finding).fix
    assert fix is not None
    return fix.edits


def test_a_range_maps_line_by_line_past_each_prefix() -> None:
    assert QUOTED.host_range(SourceRange(2, 5)) == SourceRange(14, 17)
    assert QUOTED.host_range(SourceRange(6, 11)) == SourceRange(20, 25)


def test_an_edit_across_lines_puts_each_prefix_back() -> None:
    finding = Diagnostic(
        rule_id='mid-clause-break', range=SourceRange(0, 11), message='m', fix=Fix.reflow(edit(0, 11, '# one\n# two'))
    )
    [moved] = moved_edits(finding)
    assert moved.range == SourceRange(12, 25)
    assert moved.new_text == '# one\n> # two'


def test_a_blank_line_takes_the_prefix_without_its_trailing_space() -> None:
    finding = Diagnostic(
        rule_id='mid-clause-break', range=SourceRange(0, 11), message='m', fix=Fix.reflow(edit(0, 11, '# one\n\n# two'))
    )
    [moved] = moved_edits(finding)
    assert moved.new_text == '# one\n>\n> # two'


def test_a_range_ending_where_a_line_starts_stops_short_of_its_prefix() -> None:
    assert QUOTED.host_range(SourceRange(0, 6)) == SourceRange(12, 18)


def test_an_edit_ending_in_a_newline_leaves_the_next_prefix_alone() -> None:
    finding = Diagnostic(
        rule_id='mid-clause-break', range=SourceRange(0, 6), message='m', fix=Fix.reflow(edit(0, 6, '# a\n# b\n'))
    )
    [moved] = moved_edits(finding)
    assert moved.range == SourceRange(12, 18)
    assert moved.new_text == '# a\n> # b\n'


def test_an_edit_within_one_line_maps_its_range_alone() -> None:
    finding = Diagnostic(
        rule_id='autocorrect.Spacing', range=SourceRange(8, 11), message='m', fix=Fix.reflow(edit(8, 11, 'two'))
    )
    [moved] = moved_edits(finding)
    assert (moved.range, moved.new_text) == (SourceRange(22, 25), 'two')


def test_a_document_needs_a_host_start_and_a_prefix_for_each_line() -> None:
    with pytest.raises(ValueError, match='one host start and one prefix per line'):
        EmbeddedDocument(language_name='py', text='# one\n# two\n', host_starts=(0,), prefixes=('',))
