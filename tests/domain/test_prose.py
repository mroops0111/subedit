import pytest

from subedit.domain.models import Prose
from subedit.domain.models.reflow import break_cost, reflow_sentence


def texts(prose: Prose) -> list[str]:
    return [sentence.text for sentence in prose.sentences()]


def test_empty_prose_has_no_sentences() -> None:
    assert Prose('').sentences() == ()
    assert Prose('   \n  ').sentences() == ()


def test_a_single_sentence_stays_whole() -> None:
    assert texts(Prose('cap the size to the CI limit.')) == ['cap the size to the CI limit.']


def test_sentences_split_on_terminators() -> None:
    prose = Prose('first one. second one! third one? fourth')
    assert texts(prose) == ['first one.', 'second one!', 'third one?', 'fourth']


def test_physical_lines_are_flattened_before_segmentation() -> None:
    prose = Prose('cap the size to the CI mmap limit,\nan unbounded value faults the runner.')
    assert texts(prose) == ['cap the size to the CI mmap limit, an unbounded value faults the runner.']


@pytest.mark.parametrize(
    'text',
    [
        'use a helper, e.g. the clock, before this runs',
        'the port, i.e. the interface, lives in domain',
        'compare vs. the previous value here',
        'see Smith et al. for the derivation',
        'the fix landed in No. 5 last week',
    ],
)
def test_abbreviations_do_not_end_a_sentence(text: str) -> None:
    assert len(Prose(text).sentences()) == 1


def test_no_ends_a_sentence_unless_a_number_follows() -> None:
    assert texts(Prose('just say no. then move on.')) == ['just say no.', 'then move on.']


@pytest.mark.parametrize(
    'text',
    [
        'the cap is 3.14 percent of the budget',
        'requires version 3.11 or newer to build',
        'the ratio 0.5 holds across every run',
    ],
)
def test_decimals_do_not_end_a_sentence(text: str) -> None:
    assert len(Prose(text).sentences()) == 1


@pytest.mark.parametrize(
    'text',
    [
        'see https://vale.sh/docs/formats/code for the details',
        'mirrored at www.example.com/a.b.c today',
    ],
)
def test_urls_do_not_end_a_sentence(text: str) -> None:
    assert len(Prose(text).sentences()) == 1


def test_code_spans_do_not_end_a_sentence() -> None:
    assert len(Prose('call `obj.method.chain` before the flush').sentences()) == 1


def test_an_initial_does_not_end_a_sentence() -> None:
    assert len(Prose('named after J. Smith originally').sentences()) == 1


def test_a_terminator_needs_whitespace_after_it() -> None:
    assert len(Prose('the file a.ts holds it').sentences()) == 1


def test_a_closing_quote_after_a_terminator_still_ends_the_sentence() -> None:
    assert texts(Prose('he said "stop." then left the room.')) == ['he said "stop."', 'then left the room.']


def test_sentence_offsets_address_the_flattened_text() -> None:
    prose = Prose('first one. second one.')
    first, second = prose.sentences()
    assert prose.flattened[first.offset : first.end] == 'first one.'
    assert prose.flattened[second.offset : second.end] == 'second one.'


def test_physical_lines_are_preserved_separately() -> None:
    prose = Prose('one\ntwo\nthree')
    assert prose.physical_lines == ('one', 'two', 'three')
    assert prose.flattened == 'one two three'


def test_a_backslash_b_block_is_literal_and_excluded_from_prose() -> None:
    prose = Prose('Run it.\n\n\\b example --flag value\n\\b example --other value\n\nDone.')
    literal = [segment for segment in prose.segments() if segment.is_literal]

    assert len(literal) == 1
    assert literal[0].lines == ('\\b example --flag value', '\\b example --other value')
    assert prose.flattened == 'Run it. Done.'


def test_an_indented_block_is_literal() -> None:
    prose = Prose('Summary.\n\n    code_line(1)\n    code_line(2)\n\nTrailing text.')
    assert prose.flattened == 'Summary. Trailing text.'


def test_a_fenced_block_is_literal_including_its_fences() -> None:
    prose = Prose('Before.\n```\ncode here\n```\nAfter.')
    assert prose.flattened == 'Before. After.'


def test_literal_lines_stay_available_for_rendering() -> None:
    prose = Prose('Before.\n    indented code\nAfter.')
    assert [segment.lines for segment in prose.segments()] == [
        ('Before.',),
        ('    indented code',),
        ('After.',),
    ]


def test_a_literal_block_produces_no_sentences() -> None:
    assert Prose('\\b just --an example\n').sentences() == ()


def test_prose_without_literal_blocks_is_unchanged() -> None:
    prose = Prose('cap the size to the limit,\nan unbounded value faults')
    assert [segment.is_literal for segment in prose.segments()] == [False]
    assert prose.flattened == 'cap the size to the limit, an unbounded value faults'


@pytest.mark.parametrize(
    'line',
    ['1. first item here', '2) second item', '- a bullet', '* another bullet', '+ a third', 'a. lettered item'],
)
def test_a_list_item_is_literal_structure(line: str) -> None:
    prose = Prose(f'Lead in.\n\n{line}\n\nTail prose.')
    assert any(segment.is_literal and line in segment.lines for segment in prose.segments())


def test_a_numbered_list_is_not_split_into_marker_and_body() -> None:
    prose = Prose('Order:\n\n1. Detect the flows.\n2. Pick one per entry.\n\nTail.')
    assert [sentence.text for sentence in prose.sentences()] == ['Order: Tail.']


def test_a_decimal_is_still_not_a_list_marker() -> None:
    assert len(Prose('the cap is 3.14 percent of the budget').sentences()) == 1


def test_a_wrapped_list_item_stays_with_its_marker() -> None:
    prose = Prose(
        'Steps below.\n'
        '\n'
        '1. The first step runs,\n'
        '   and this line continues it rather than opening a paragraph.\n'
        '2. The second step.'
    )
    literal_text = [segment.lines for segment in prose.segments() if segment.is_literal]

    assert any('and this line continues it' in line for lines in literal_text for line in lines), (
        'a continuation indented under its marker belongs to the item, not to the prose around it'
    )


def test_a_list_ends_at_a_blank_line() -> None:
    prose = Prose('1. An item.\n\nA paragraph that follows.')
    trailing = [segment for segment in prose.segments() if not segment.is_literal]

    assert any('A paragraph that follows.' in line for segment in trailing for line in segment.lines)


def test_an_unindented_line_after_a_list_is_prose_again() -> None:
    prose = Prose('1. An item.\nA sentence at the left margin.')
    flowing = [segment for segment in prose.segments() if not segment.is_literal]

    assert any('A sentence at the left margin.' in line for segment in flowing for line in segment.lines)


def test_a_possessive_ends_its_sentence() -> None:
    prose = Prose("The audience is the gateway's URI, never the upstream API's. The spec requires it.")
    assert texts(prose) == ["The audience is the gateway's URI, never the upstream API's.", 'The spec requires it.']


def test_a_period_inside_brackets_ends_no_sentence() -> None:
    prose = Prose('headers (``Authorization``, ``X-API-Key``, ...) they want on the request.')
    assert len(prose.sentences()) == 1


@pytest.mark.parametrize(
    ('sentence', 'expected'),
    [
        ('a list (one, two, three) and then, a clause.', ('a list (one, two, three) and then,', 'a clause.')),
        ('the names ``a, b`` and more, then a clause.', ('the names ``a, b`` and more,', 'then a clause.')),
        ('1) a stray bracket, then a clause.', ('1) a stray bracket,', 'then a clause.')),
    ],
)
def test_only_a_comma_outside_brackets_and_code_breaks_a_sentence(sentence: str, expected: tuple[str, ...]) -> None:
    assert reflow_sentence(sentence, width=len(sentence) - 1) == expected


def test_a_break_lands_between_clauses_rather_than_inside_a_list() -> None:
    sentence = (
        'Goes through the full Gateway assembly, so the auth resolver, base URL, '
        'and URI-template-driven kwarg passing are all exercised together.'
    )
    assert reflow_sentence(sentence, width=100) == (
        'Goes through the full Gateway assembly,',
        'so the auth resolver, base URL, and URI-template-driven kwarg passing are all exercised together.',
    )


def test_a_brief_clause_standing_alone_is_no_list_item() -> None:
    pieces = ('A pointer into a component,', 'or a name outside the grammar,', 'returns ``None``,', 'so it is inlined.')
    lines = (' '.join(pieces[:3]), pieces[3])
    assert break_cost(lines) == 0


def test_fewer_lines_outrank_a_clause_boundary() -> None:
    sentence = 'first clause here, second clause, third clause that runs on.'
    assert len(reflow_sentence(sentence, width=40)) == 2


def test_an_appositive_is_no_list_item() -> None:
    lines = (
        'The extension adds a field and a required name to ``owner``, a ``Person``,',
        'and types ``approver``, a ``Reviewer`` in ``Base``, by a second component, ``Admin``.',
    )
    assert break_cost(lines) == 0


def test_parallel_items_led_by_articles_still_form_a_list() -> None:
    lines = ('It feeds a cat, a dog,', 'and a bird every morning before the long walk.')
    assert break_cost(lines) == 1


@pytest.mark.parametrize(
    'text',
    [
        'Process-local pub/sub of `WorkspaceEvent`s. Subscribers register per workspace.',
        'Stop both on Ctrl+C. Standalone, it runs the server alone.',
        'Retry on HTTP 5xx-A. Then give up.',
    ],
)
def test_a_letter_closing_a_longer_token_is_no_initial(text: str) -> None:
    assert len(Prose(text).sentences()) == 2


def test_an_initial_in_brackets_still_holds_its_sentence() -> None:
    assert len(Prose('named after (J. Smith) originally').sentences()) == 1


def test_a_break_before_such_as_falls_ahead_of_the_list_it_opens() -> None:
    lines = (
        'Holds everything that carries user content and ages out on its own,',
        'such as history, parked approvals, dedupe keys and the in-chat OAuth handoff.',
    )
    assert break_cost(lines) == 0
