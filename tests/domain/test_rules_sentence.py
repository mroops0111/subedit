import pytest
from factories import document, found, rule_set
from factories import fixed as fix_document
from factories import lint as lint_document

from subedit.domain import FixKind, Report, RuleSettings, Severity


REWRITE_IDS = frozenset({'line-too-short', 'unbreakable-sentence', 'mid-list-break'})

LIST_SENTENCE = (
    'Write only what to draw, which is inline `data.values` rows taken from tool results, `mark`, '
    '`encoding`, and optionally `transform` or `layer`.'
)


def lint(
    source: str, width: int = 50, enabled_rule_ids: frozenset[str] = REWRITE_IDS, **settings: RuleSettings
) -> Report:
    return lint_document(document(source), rule_set(enabled_rule_ids, width, settings))


def ids(source: str, **kwargs) -> list[str]:
    return found(lint(source, **kwargs))


def comment(text: str) -> str:
    return f'def f():\n    # {text}\n    pass\n'


def test_a_short_standalone_sentence_is_not_a_stub() -> None:
    assert ids(comment('brief.')) == []


def test_a_sentence_that_fits_is_never_flagged() -> None:
    assert ids(comment('this one fits inside the budget fine.')) == []


def test_a_forced_break_leaving_a_stub_is_reported() -> None:
    assert 'line-too-short' in ids(comment('cap the size to the shared runner ceiling limit that we set here, ok.'))


def test_a_balanced_split_is_not_a_stub() -> None:
    assert 'line-too-short' not in ids(comment('cap the size to the runner limit, an unbounded value faults it.'))


def test_the_stub_floor_is_configurable() -> None:
    source = comment('cap the size to the runner limit, an unbounded value faults it.')
    assert 'line-too-short' in ids(source, **{'line-too-short': RuleSettings(options={'min-line-characters': 40})})


def test_a_long_sentence_with_no_comma_is_unbreakable() -> None:
    assert 'unbreakable-sentence' in ids(comment('this single sentence has no comma anywhere and runs well past it.'))


def test_a_long_sentence_with_a_comma_is_breakable() -> None:
    assert 'unbreakable-sentence' not in ids(comment('this sentence is long, but it carries a comma to break at.'))


def test_a_short_sentence_without_a_comma_is_fine() -> None:
    assert 'unbreakable-sentence' not in ids(comment('no comma here.'))


def test_rewrite_diagnostics_carry_no_edits_and_reach_the_author() -> None:
    report = lint(comment('this single sentence has no comma anywhere and runs well past it.'))
    for item in report.needing_author:
        assert item.fix is not None
        assert item.fix.kind is FixKind.REWRITE
        assert item.fix.edits == ()
        assert not item.is_mechanical


def test_the_message_states_the_concrete_fix() -> None:
    report = lint(comment('this single sentence has no comma anywhere and runs well past it.'))
    message = report.needing_author[0].message
    assert 'no comma' in message
    assert 'Add a comma' in message or 'split it into two sentences' in message


def test_the_stub_message_quotes_the_offending_fragment() -> None:
    report = lint(comment('cap the size to the shared runner ceiling limit that we set here, ok.'))
    stub = next(item for item in report.needing_author if item.rule_id == 'line-too-short')
    assert '"ok."' in stub.message


def test_a_literal_block_is_never_flagged() -> None:
    source = 'def f():\n    """Summary.\n\n        a_very_long_literal_line_with_no_comma_at_all_here_indeed(1234567890)\n    """\n'
    assert ids(source) == []


def test_the_budget_shrinks_with_indentation() -> None:
    text = 'this sentence has no comma and sits at some depth in the file.'
    shallow = f'def a():\n    # {text}\n    pass\n'
    deep = f'def a():\n    def b():\n        def c():\n            # {text}\n            pass\n'
    width = len(f'    # {text}') + 1

    assert 'unbreakable-sentence' not in ids(shallow, width=width)
    assert 'unbreakable-sentence' in ids(deep, width=width)


@pytest.mark.parametrize('rule_id', sorted(REWRITE_IDS))
def test_each_rule_can_be_disabled_independently(rule_id: str) -> None:
    source = comment('cap the size to the shared runner ceiling limit that we set here, ok.')
    assert rule_id not in ids(source, enabled_rule_ids=REWRITE_IDS - {rule_id})


def test_a_clause_too_long_to_fit_is_unbreakable_despite_other_commas() -> None:
    text = 'an opening clause long enough, and then a much longer clause carrying no further comma at all.'
    assert ids(comment(text), width=60) == ['unbreakable-sentence']


def test_a_sentence_that_breaks_only_inside_a_list_is_a_warning() -> None:
    text = 'No auth, a static bearer or api key, and an oauth2 service token all call the API as one identity.'
    [finding] = lint(comment(text), width=80).diagnostics
    assert (finding.rule_id, finding.severity) == ('mid-list-break', Severity.WARNING)


def test_a_docstring_summary_too_long_for_one_line_needs_its_author() -> None:
    source = 'def f():\n    """Return the code, state, and iss of the redirect once the user completes the flow."""\n'
    report = lint(source, width=80)
    assert [item.rule_id for item in report.diagnostics] == ['unbreakable-sentence']
    assert 'PEP 257' in report.diagnostics[0].message


def test_a_summary_that_fits_beside_its_quotes_is_fine() -> None:
    assert ids('def f():\n    """Return the code once the user completes the flow."""\n', width=80) == []


def test_a_summary_the_author_wrapped_still_needs_shortening() -> None:
    source = 'def f():\n    """Return the code, state, and iss of the redirect\n    once the user completes the flow.\n    """\n'
    assert ids(source, width=80) == ['unbreakable-sentence'], 'a wrapped summary is as far from one line as a long one'


def docstring(*lines: str) -> str:
    body = ''.join(f'        {line}\n' for line in lines)
    return f'class Chart:\n    def draw(self) -> None:\n        """Draw a chart.\n\n{body}        """\n'


@pytest.mark.parametrize(
    'lines',
    [
        (LIST_SENTENCE,),
        (LIST_SENTENCE[: LIST_SENTENCE.index('`encoding`') - 1], LIST_SENTENCE[LIST_SENTENCE.index('`encoding`') :]),
    ],
    ids=['on one line', 'broken inside the list'],
)
def test_a_sentence_that_splits_a_list_wherever_it_breaks_is_left_to_its_reader(lines: tuple[str, ...]) -> None:
    assert ids(docstring(*lines), width=120, enabled_rule_ids=REWRITE_IDS) == ['mid-list-break']


def test_a_sentence_broken_inside_a_list_keeps_the_layout_its_author_gave_it() -> None:
    source = docstring(
        LIST_SENTENCE[: LIST_SENTENCE.index('`encoding`') - 1], LIST_SENTENCE[LIST_SENTENCE.index('`encoding`') :]
    )
    assert fix_document(document(source)) == source


@pytest.mark.parametrize(
    'source',
    [
        comment(
            'A ``$ref`` to a component schema stays a reference, rewritten to ``#/$defs/<Name>``,\n'
            '    # and the component itself is expanded once into ``defs`` under its name.'
        ),
        comment(
            'A person for anything a route starts, batch included,\n'
            "    # and the service account itself for an autonomous run such as the reactor's."
        ),
    ],
    ids=['participle', 'absolute phrase'],
)
def test_a_break_after_an_aside_the_list_check_mistakes_for_an_item_keeps_its_layout(source: str) -> None:
    every_rule = rule_set(width=100)
    assert fix_document(document(source), every_rule) == source
    assert all(item.severity is Severity.WARNING for item in lint_document(document(source), every_rule).diagnostics)


def test_a_shorter_item_limit_reads_fewer_pieces_as_list_items() -> None:
    source = comment(
        'No auth, a static bearer or api key, and an oauth2 service token all call the API as one identity.'
    )
    settings = {'mid-list-break': RuleSettings(options={'max-item-words': 1})}
    assert ids(source, width=80) == ['mid-list-break']
    assert ids(source, width=80, **settings) == []


def test_a_project_that_switches_the_list_rule_off_leaves_lists_out_of_reflow() -> None:
    source = comment(
        'Goes through the full Gateway assembly, so the auth resolver, base URL, '
        'and URI-template-driven kwarg passing are all exercised together.'
    )
    with_lists = fix_document(document(source), rule_set(width=106))
    without_lists = fix_document(document(source), rule_set(frozenset({'mid-clause-break'}), width=106))
    assert '# Goes through the full Gateway assembly,\n' in with_lists
    assert '# Goes through the full Gateway assembly, so the auth resolver, base URL,\n' in without_lists
