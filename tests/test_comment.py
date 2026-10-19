import dataclasses

import pytest

from subedit.domain import (
    CommentForm,
    CommentGroup,
    CommentLine,
    CommentPlacement,
    SourceRange,
    SymbolKind,
    SymbolRef,
    Visibility,
)


def line(text: str, indent: str = '  ', delimiter: str = '// ', start: int = 0) -> CommentLine:
    return CommentLine(SourceRange(start, start + 1), indent, delimiter, text)


def group(*bodies: str, **kwargs: object) -> CommentGroup:
    defaults: dict[str, object] = {
        'range': SourceRange(0, 10),
        'lines': tuple(line(body) for body in bodies),
        'form': CommentForm.LINE,
        'placement': CommentPlacement.INLINE_BODY,
    }
    defaults.update(kwargs)
    return CommentGroup(**defaults)  # pyright: ignore[reportArgumentType]


def rebuilt(subject: CommentGroup, *texts: str) -> CommentGroup:
    return dataclasses.replace(subject, lines=subject.layout.rebuild(subject.lines, texts, width=80))


def test_a_block_needs_at_least_one_line() -> None:
    with pytest.raises(ValueError, match='at least one line'):
        CommentGroup(
            range=SourceRange(0, 1),
            lines=(),
            form=CommentForm.LINE,
            placement=CommentPlacement.INLINE_BODY,
        )


def test_physical_width_counts_indent_and_delimiter_not_just_text() -> None:
    indent, delimiter, body = ' ' * 40, '// ', 'content'
    subject = line(body, indent=indent, delimiter=delimiter)

    assert subject.physical_width == len(indent) + len(delimiter) + len(body)
    assert subject.prefix_width == len(indent) + len(delimiter)
    assert subject.physical_width > len(body)


def test_widest_line_is_measured_across_the_block() -> None:
    subject = group('short', 'a much longer text here')
    assert subject.longest_line == len('  // ') + len('a much longer text here')


def test_prose_strips_markers_and_joins_lines() -> None:
    subject = group('cap the size to the limit,', 'an unbounded value faults')
    assert subject.prose().physical_lines == ('cap the size to the limit,', 'an unbounded value faults')
    assert subject.prose().flattened == 'cap the size to the limit, an unbounded value faults'


def test_rendering_round_trips_the_prefix() -> None:
    assert group('alpha', 'beta').render() == '  // alpha\n  // beta'


def test_an_empty_payload_renders_without_trailing_space() -> None:
    assert group('').render() == '  //'


def test_with_payloads_returns_a_new_block_and_leaves_the_original_alone() -> None:
    original = group('one', 'two')
    rewrapped = rebuilt(original, 'single line now')

    assert rewrapped is not original
    assert original.line_count == 2
    assert rewrapped.line_count == 1
    assert rewrapped.render() == '  // single line now'


def test_with_payloads_can_grow_the_block_using_the_first_line_prefix() -> None:
    grown = rebuilt(group('one'), 'one', 'two', 'three')
    assert grown.render() == '  // one\n  // two\n  // three'


def test_with_payloads_rejects_an_empty_result() -> None:
    with pytest.raises(ValueError, match='at least one line'):
        rebuilt(group('one'))


def documented(name: str, visibility: Visibility) -> CommentGroup:
    return group(
        'doc',
        placement=CommentPlacement.LEADING_DECLARATION,
        attachment=SymbolRef(name, SymbolKind.FUNCTION, visibility),
    )


def test_public_attachment_is_reported() -> None:
    assert documented('buildProposal', Visibility.PUBLIC).attaches_to_public_symbol
    assert not documented('_helper', Visibility.INTERNAL).attaches_to_public_symbol
    assert not group('doc').attaches_to_public_symbol


@pytest.mark.parametrize(
    'placement',
    [CommentPlacement.FILE_HEADER, CommentPlacement.INLINE_BODY, CommentPlacement.TRAILING],
)
def test_only_a_leading_declaration_may_document_a_symbol(placement: CommentPlacement) -> None:
    with pytest.raises(ValueError, match='Only a leading declaration'):
        group(
            'doc',
            placement=placement,
            attachment=SymbolRef('build', SymbolKind.FUNCTION, Visibility.PUBLIC),
        )


def test_as_edit_targets_the_block_range() -> None:
    subject = group('alpha', range=SourceRange(4, 40))
    edit = subject.as_edit()
    assert edit.range == SourceRange(4, 40)
    assert edit.new_text == '  // alpha'


def test_prose_preserves_indentation_relative_to_the_block() -> None:
    lines = (
        CommentLine(SourceRange(0, 1), '    ', '', 'Summary.'),
        CommentLine(SourceRange(1, 2), '', '', ''),
        CommentLine(SourceRange(2, 3), '        ', '', 'indented_code()'),
        CommentLine(SourceRange(3, 4), '    ', '', 'Trailing.'),
    )
    group = CommentGroup(
        range=SourceRange(0, 4),
        lines=lines,
        form=CommentForm.DOC,
        placement=CommentPlacement.LEADING_DECLARATION,
    )
    assert group.prose().physical_lines == ('Summary.', '', '    indented_code()', 'Trailing.')
    assert group.prose().flattened == 'Summary. Trailing.'


def test_prose_keeps_uniformly_indented_lines_flush() -> None:
    lines = tuple(
        CommentLine(SourceRange(index, index + 1), '        ', '# ', text) for index, text in enumerate(('one', 'two'))
    )
    group = CommentGroup(
        range=SourceRange(0, 2),
        lines=lines,
        form=CommentForm.LINE,
        placement=CommentPlacement.INLINE_BODY,
    )
    assert group.prose().physical_lines == ('one', 'two')
