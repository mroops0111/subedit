import pytest
from factories import commit_message, markdown, rule_set

from subedit.application import CorpusMeter, CorpusStatistics, Distribution, OptionStatistics, SurfaceStatistics
from subedit.domain import Document, RuleSettings
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER


def measure_all(*documents: Document) -> CorpusStatistics:
    return CorpusMeter(DEFAULT_PARSER).run(documents)


def measure(*sources: str) -> SurfaceStatistics:
    documents = tuple(
        Document(uri=f'file:///a{index}.py', text=source, language_id='python') for index, source in enumerate(sources)
    )
    measured = measure_all(*documents).for_surface('comments')
    assert measured is not None
    return measured


def test_an_empty_corpus_reports_nothing() -> None:
    assert measure_all().surfaces == ()


def test_each_surface_is_measured_apart() -> None:
    measured = measure_all(
        Document(uri='file:///a.py', text='# note.\n', language_id='python'),
        markdown('# Notes\n\nA paragraph of two sentences. It ends here.\n'),
        commit_message('Add the parser\n\nIt reads the subject.\n'),
    )

    assert [surface.surface for surface in measured.surfaces] == ['comments', 'markdown', 'commit-messages']
    prose = measured.for_surface('markdown')
    assert prose is not None
    assert prose.sentence_lengths.count >= 2
    assert prose.line_counts == (), 'a Markdown block is not laid out in lines, so it has no line count'
    body = measured.for_surface('commit-messages')
    assert body is not None
    assert [distribution.label for distribution in body.line_counts] == ['all']


def test_percentiles_on_an_empty_distribution_are_zero() -> None:
    empty = Distribution('none', ())
    assert empty.percentile(0.9) == 0
    assert empty.maximum == 0
    assert empty.median == 0


def test_percentiles_bracket_the_data() -> None:
    distribution = Distribution('d', tuple(range(1, 101)))
    assert distribution.percentile(0.0) == 1
    assert distribution.percentile(1.0) == 100
    assert distribution.median == 50
    assert distribution.percentile(0.5) <= distribution.percentile(0.9) <= distribution.maximum


def test_blocks_group_by_form_placement_and_visibility() -> None:
    report = measure(
        'def build():\n    """Public doc."""\n',
        'def _helper():\n    """Internal doc."""\n',
        'def f():\n    # inline\n    pass\n',
        'x = 1  # trailing\n',
    )
    labels = {distribution.label for distribution in report.line_counts}
    assert labels == {'doc/public', 'doc/internal', 'plain/inline-body', 'plain/trailing'}
    public = next(item for item in report.line_counts if item.label == 'doc/public')
    assert public.count == 1


def test_physical_width_measures_the_source_line_not_the_payload() -> None:
    indent = ' ' * 40
    report = measure(f'def a():\n{indent}# short\n')
    assert report.physical_widths.maximum == len(f'{indent}# short')


def test_an_unbreakable_sentence_is_one_that_is_long_with_no_comma() -> None:
    breakable = 'x = 1  # ' + 'word ' * 30 + 'and, a comma here.\n'
    unbreakable = 'y = 2  # ' + 'word ' * 30 + 'no comma at all.\n'
    report = measure(breakable, unbreakable)
    counts = dict(report.unbreakable_counts_by_width)
    assert counts[80] == 1
    assert counts[120] == 1


def test_a_short_sentence_is_never_unbreakable() -> None:
    report = measure('# brief note.\n')
    assert all(count == 0 for _, count in report.unbreakable_counts_by_width)


@pytest.mark.parametrize('width', [72, 80, 88, 100, 120])
def test_every_configured_width_is_reported(width: int) -> None:
    assert width in dict(measure('# note.\n').unbreakable_counts_by_width)


def test_unbreakable_counts_fall_as_the_width_rises() -> None:
    source = '# ' + 'word ' * 20 + 'without any comma.\n'
    counts = [count for _, count in sorted(measure(source).unbreakable_counts_by_width)]
    assert counts == sorted(counts, reverse=True)


def options_of(*documents: Document, settings: dict[str, RuleSettings] | None = None) -> dict[str, OptionStatistics]:
    measured = CorpusMeter(DEFAULT_PARSER, ALL_RULES).run(documents, lambda _: rule_set((), 50, settings))
    return {
        f'{option.rule_id} {option.option.name}': option for surface in measured.surfaces for option in surface.options
    }


def values(options: dict[str, OptionStatistics], name: str) -> tuple[int, ...]:
    return tuple(sorted(options[name].distribution.measurements))


def test_a_comment_is_measured_against_the_limit_for_its_kind() -> None:
    options = options_of(Document(uri='file:///a.py', text='# one.\n# two.\nx = 1\n', language_id='python'))

    assert values(options, 'comment-too-long max-plain-lines') == (2,)
    assert values(options, 'comment-too-long max-public-doc-lines') == ()


def test_a_broken_sentence_is_measured_by_its_shortest_line_with_no_minimum_set() -> None:
    sentence = 'the cache keeps every entry it reads from disk, so a second read is quick'
    options = options_of(Document(uri='file:///a.py', text=f'x = 1\n# {sentence}.\n', language_id='python'))

    assert values(options, 'line-too-short min-line-characters') == (len('so a second read is quick.'),)


def test_the_items_of_a_serial_list_are_measured_in_words() -> None:
    sentence = 'It reads files, the rule engine, a fixer, and the rest.'
    options = options_of(Document(uri='file:///a.py', text=f'# {sentence}\nx = 1\n', language_id='python'))

    assert values(options, 'mid-list-break max-item-words') == (2, 3)


def test_each_kind_of_label_is_measured_against_its_own_limit() -> None:
    options = options_of(
        markdown(
            'A lead.\n\n- **Bold Label Here**: text.\n- Plain label: text.\n'
            '- ＷＩＤＥ：text.\n'  # noqa: RUF001
            '- The cache is warm: a clause.\n\nNote: a tag.\n'
        )
    )

    assert values(options, 'mid-sentence-colon max-bold-label-words') == (3,)
    assert values(options, 'mid-sentence-colon max-label-words') == (2,)
    assert values(options, 'mid-sentence-colon max-full-width-label-characters') == (4,)
    assert values(options, 'mid-sentence-colon max-tag-words') == (1,)


def test_a_commit_subject_is_measured_in_characters() -> None:
    options = options_of(commit_message('Add the parser\n'))

    assert values(options, 'subject-too-long max-subject-characters') == (len('Add the parser'),)


def test_an_option_shows_the_value_the_project_sets_beside_its_default() -> None:
    options = options_of(
        commit_message('Add the parser\n'),
        settings={'subject-too-long': RuleSettings(options={'max-subject-characters': 50})},
    )

    measured = options['subject-too-long max-subject-characters']
    assert (measured.option.default, measured.setting) == (72, 50)


def test_a_rule_is_measured_even_when_the_project_runs_it_not() -> None:
    measured = CorpusMeter(DEFAULT_PARSER, ALL_RULES).run((commit_message('Add the parser\n'),), lambda _: rule_set(()))

    surface = measured.for_surface('commit-messages')
    assert surface is not None
    assert any(option.rule_id == 'subject-too-long' for option in surface.options)


def test_a_surface_no_rule_measures_has_no_options() -> None:
    assert measure('# note.\n').options == (), 'a meter given no rules measures no option'
