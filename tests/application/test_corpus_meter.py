import pytest

from subedit.application import CorpusMeter, Distribution
from subedit.domain import Document
from subedit.infrastructure import COMMENT_PARSER


def measure(*sources: str):
    documents = tuple(
        Document(uri=f'file:///a{index}.py', text=source, language_id='python') for index, source in enumerate(sources)
    )
    return CorpusMeter(COMMENT_PARSER).run(documents)


def test_an_empty_corpus_reports_nothing() -> None:
    report = measure()
    assert report.document_count == 0
    assert report.group_count == 0
    assert report.physical_widths.count == 0


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
    assert labels == {'doc/public', 'doc/internal', 'line/inline-body', 'line/trailing'}
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
