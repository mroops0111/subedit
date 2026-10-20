import pytest

from subedit.application import Linter, RuleEngine
from subedit.domain import Document, FixKind, RuleSet, apply_edits
from subedit.infrastructure import DEFAULT_PARSER, LAYOUT_RULES


ALL_LAYOUT = frozenset({'mid-clause-break', 'line-too-long'})


def lint(source: str, width: int = 60, enabled_rule_ids: frozenset[str] = ALL_LAYOUT):
    document = Document(uri='file:///a.py', text=source, language_id='python')
    return Linter(DEFAULT_PARSER, RuleEngine(LAYOUT_RULES)).run(
        document, RuleSet(enabled_rule_ids=enabled_rule_ids, line_width=width)
    )


def fixed(source: str, width: int = 60) -> str:
    report = lint(source, width)
    edits = tuple(edit for item in report.mechanical if item.fix for edit in item.fix.edits)
    return apply_edits(source, edits[:1]) if edits else source


def test_already_correct_layout_is_clean() -> None:
    assert lint('def f():\n    # one sentence here.\n    pass\n').is_clean


def test_a_mid_clause_break_is_reported_and_reflowed() -> None:
    source = 'def f():\n    # cap the size to the limit so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    report = lint(source, width=70)
    assert 'mid-clause-break' in [item.rule_id for item in report.diagnostics]
    assert '# cap the size to the limit so the mmap does not blow past it,\n' in fixed(source, width=70)


def test_short_sentences_sharing_a_line_that_fits_stay_together() -> None:
    assert lint('def f():\n    # first one. second one. third one.\n    pass\n').is_clean


def test_sentences_sharing_a_line_that_overflows_take_one_line_each() -> None:
    source = 'def f():\n    # the first sentence runs on. the second one too. the third one ends here.\n    pass\n'
    assert fixed(source, width=40).count('    # ') == 3


def test_sentences_on_lines_of_their_own_are_not_joined() -> None:
    assert lint('def f():\n    # first one.\n    # second one.\n    pass\n').is_clean


def test_a_sentence_running_on_from_a_shared_line_takes_its_own_line() -> None:
    source = 'def f():\n    # first one. second one\n    # runs on.\n    pass\n'
    assert fixed(source) == 'def f():\n    # first one.\n    # second one runs on.\n    pass\n'


def test_a_docstring_summary_keeps_its_line_to_itself() -> None:
    source = 'def f():\n    """Do it. Then more.\n\n    Body.\n    """\n'
    assert '"""Do it.\n\n    Then more.' in fixed(source)


def test_a_long_sentence_splits_at_commas_only() -> None:
    source = 'def f():\n    # this is long indeed, it carries clauses, and it ends here.\n    pass\n'
    for line in fixed(source, width=40).splitlines():
        if line.strip().startswith('#'):
            assert line.rstrip().endswith((',', '.')) or line.strip() == '#'


def test_a_sentence_with_no_comma_is_left_alone_by_reflow() -> None:
    source = 'def f():\n    # this single sentence has no comma at all and cannot be split anywhere.\n    pass\n'
    assert fixed(source, width=40) == source


def test_line_width_counts_indent_and_marker() -> None:
    text = 'a padded text here, and a tail clause that follows.'
    shallow = f'def a():\n    # {text}\n    pass\n'
    deep = f'def a():\n    def b():\n        def c():\n            # {text}\n            pass\n'

    width = len(f'    # {text}') + 1
    assert 'line-too-long' not in [item.rule_id for item in lint(shallow, width=width).diagnostics]
    assert 'line-too-long' in [item.rule_id for item in lint(deep, width=width).diagnostics]


def test_line_width_stays_silent_when_the_block_already_fits() -> None:
    source = 'def f():\n    # short.\n    pass\n'
    assert 'line-too-long' not in [item.rule_id for item in lint(source, width=80).diagnostics]


def test_line_width_stays_silent_when_reflow_cannot_help() -> None:
    long_word = 'a' * 90
    source = f'def f():\n    # {long_word}.\n    pass\n'
    assert 'line-too-long' not in [item.rule_id for item in lint(source, width=40).diagnostics]


def test_layout_fixes_are_reflow_kind() -> None:
    source = 'def f():\n    # one. two.\n    pass\n'
    for item in lint(source).diagnostics:
        assert item.fix is not None
        assert item.fix.kind is FixKind.REFLOW
        assert item.is_mechanical


def test_reflow_is_idempotent_on_its_own_output() -> None:
    source = 'def f():\n    # cap the size to the limit so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    once = fixed(source)
    assert fixed(once) == once


def test_a_docstring_keeps_its_delimiters_through_reflow() -> None:
    source = 'def f():\n    """Summary here, with a clause that runs on and on and needs a split.\n    """\n'
    result = fixed(source, width=40)
    assert result.count('"""') == 2
    assert result.rstrip().endswith('"""')


def test_a_single_line_docstring_stays_on_one_line() -> None:
    source = 'def f():\n    """Short."""\n'
    assert fixed(source, width=80) == source


def test_a_literal_block_survives_reflow_untouched() -> None:
    source = 'def f():\n    """Summary.\n\n        literal_code(1)\n\n    Tail prose, with a comma.\n    """\n'
    assert '        literal_code(1)' in fixed(source, width=40)


@pytest.mark.parametrize('rule_id', sorted(ALL_LAYOUT))
def test_each_rule_can_be_disabled_independently(rule_id: str) -> None:
    source = 'def f():\n    # cap the size to the limit so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n'
    ids = [item.rule_id for item in lint(source, enabled_rule_ids=ALL_LAYOUT - {rule_id}).diagnostics]
    assert rule_id not in ids


def test_an_unbreakable_sentence_still_gets_a_canonical_line() -> None:
    source = 'def f():\n    # first one, with a comma. a second sentence with no comma runs past the budget here.\n    pass\n'
    result = fixed(source, width=60)

    assert '    # first one, with a comma.\n' in result
    assert '    # a second sentence with no comma runs past the budget here.\n' in result


def test_a_fixable_neighbour_is_repaired_even_beside_an_unbreakable_sentence() -> None:
    source = (
        'def f():\n'
        '    # cap the size to the shared limit so the mmap does not\n'
        '    # blow past it, an unbounded value faults the runner.\n'
        '    # this one carries no comma at all and runs a very long way past the budget.\n'
        '    pass\n'
    )
    result = fixed(source, width=74)
    assert '# cap the size to the shared limit so the mmap does not blow past it,\n' in result


def test_a_numbered_list_survives_reflow() -> None:
    source = 'def f():\n    """Order:\n\n    1. Detect the flows first.\n    2. Pick one per entry, otherwise fall back.\n    """\n'
    result = fixed(source, width=60)
    assert '1. Detect the flows first.' in result
    assert '2. Pick one per entry, otherwise fall back.' in result


def test_a_sentence_that_fits_comes_back_onto_one_line() -> None:
    source = (
        'def f():\n    # an unknown key is a mistake,\n    # and dropping one is worse than refusing it.\n    pass\n'
    )
    assert '    # an unknown key is a mistake, and dropping one is worse than refusing it.\n' in fixed(source, width=80)


def test_a_needed_break_at_a_clause_comma_is_left_alone() -> None:
    source = (
        'def f():\n'
        '    # Goes through the full Gateway assembly,\n'
        '    # so the auth resolver, base URL, and URI-template-driven kwarg passing are all exercised together.\n'
        '    pass\n'
    )
    assert lint(source, width=110).is_clean


def test_a_docstring_line_counts_its_own_indent_not_the_opening_quotes() -> None:
    sentence = 'x' * 60 + ', so rotation needs no restart and nothing else changes for it.'
    source = f'class C:\n    """Verify tokens.\n\n    {sentence}\n    """\n'
    width = len(f'    {sentence}')
    assert lint(source, width=width).is_clean


def test_a_one_line_docstring_leaves_room_for_its_closing_quotes() -> None:
    source = 'def f():\n    """' + 'x' * 40 + ',\n    ' + 'y' * 10 + '.\n    """\n'
    assert lint(source, width=60).is_clean, 'joined, the line with its closing quotes would run to 62'


def test_a_bracketed_ellipsis_is_not_a_place_to_break() -> None:
    source = (
        'class C:\n'
        '    """Resolve headers.\n\n'
        '    Implementations return the headers (``Authorization``, ``X-API-Key``, ...) they want,\n'
        '    and the generator merges that dict in unchanged.\n'
        '    """\n'
    )
    assert lint(source, width=90).is_clean


def test_a_line_ending_on_a_colon_keeps_its_layout_for_the_rewrite() -> None:
    source = (
        'def f():\n'
        '    # Both legs stay separate, which is what the spec requires:\n'
        '    # the caller token is accepted only because it names this endpoint.\n'
        '    pass\n'
    )
    assert lint(source, width=120).is_clean, 'the colon needs its author, and moving it mid line reads worse'


def test_a_docstring_summary_is_never_broken() -> None:
    source = 'def f():\n    """Return the code, state, and iss of the redirect once the user completes the flow."""\n'
    assert fixed(source, width=80) == source, 'PEP 257 keeps the summary to one line, so a long one waits for a rewrite'


def test_a_serial_list_with_one_long_item_is_not_split() -> None:
    source = (
        'def f():\n'
        '    """Pick a kind.\n\n'
        '    No auth, a static ``bearer`` or ``api_key``, and an ``oauth2`` service token all call\n'
        '    the API as one shared identity.\n'
        '    """\n'
    )
    assert fixed(source, width=90) == source


def test_a_line_comment_list_stays_right_under_its_introduction() -> None:
    source = (
        "# Where a card's suggestions land in the final message.\n"
        "# * 'chip': quick-reply chips at message-envelope level\n"
        "# * 'button': inline buttons in the bubble footer\n"
        "PLACEMENT = 'chip'\n"
    )
    assert fixed(source, width=120) == source, 'a blank line added here would push the block past its line limit'


def test_a_docstring_list_still_gets_the_blank_line_rest_needs() -> None:
    source = 'def f():\n    """Pick one.\n\n    The order is fixed.\n    - detect\n    - pick\n    """\n'
    assert '    The order is fixed.\n\n    - detect\n' in fixed(source, width=120)


def test_a_trailing_comment_is_never_broken_onto_a_line_of_its_own() -> None:
    source = 'x = compute()  # a trailing note, which runs well past the width set for this file\n'
    assert fixed(source, width=60) == source, 'a second line would copy the code beside the comment'


def test_a_trailing_comment_over_the_width_asks_for_its_author() -> None:
    source = 'x = compute()  # a trailing note, which runs well past the width set for this file\n'
    report = lint(source, width=60)
    assert [item.rule_id for item in report.diagnostics] == ['line-too-long']
    assert report.diagnostics[0].fix is not None
    assert report.diagnostics[0].fix.kind is FixKind.REWRITE


def test_a_paragraph_moved_onto_a_blank_line_keeps_its_space() -> None:
    source = (
        'def f():\n    # the first paragraph runs on\n    # past one line.\n    #\n    # the second one.\n    pass\n'
    )
    assert fixed(source, width=60) == (
        'def f():\n    # the first paragraph runs on past one line.\n    #\n    # the second one.\n    pass\n'
    )
