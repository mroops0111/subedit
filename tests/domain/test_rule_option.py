import pytest

from subedit.domain import (
    ChoiceOption,
    CountOption,
    HeadingLevelsOption,
    ReplacementsOption,
    RuleOption,
    RuleSettings,
    WordsOption,
)


def test_an_option_the_project_leaves_unset_takes_its_default() -> None:
    width = CountOption('width', 120)
    assert RuleSettings(options={'width': 90}).value(width) == 90
    assert RuleSettings().value(width) == 120


@pytest.mark.parametrize(
    ('option', 'value', 'accepted'),
    [
        pytest.param(CountOption('limit', 3), 0, True, id='count of zero'),
        pytest.param(CountOption('limit', 3), -1, False, id='negative count'),
        pytest.param(CountOption('limit', 3), True, False, id='boolean as a count'),
        pytest.param(ChoiceOption('style', 'a', choices=('a', 'b')), 'c', False, id='unlisted choice'),
        pytest.param(WordsOption('words', ()), ['npm', 3], False, id='word list holding a number'),
        pytest.param(HeadingLevelsOption('levels', ()), [1, 6], True, id='heading levels'),
        pytest.param(HeadingLevelsOption('levels', ()), [7], False, id='heading level past six'),
        pytest.param(ReplacementsOption('replacements', {}), {'utilize': 'use'}, True, id='replacement'),
        pytest.param(ReplacementsOption('replacements', {}), {'utilize': ''}, False, id='empty replacement'),
        pytest.param(
            ReplacementsOption('replacements', {}), {'cancel': 'cancel out'}, False, id='replacement replaced again'
        ),
    ],
)
def test_an_option_accepts_only_values_of_its_kind(option: RuleOption[object], value: object, accepted: bool) -> None:
    assert option.accepts(value) is accepted


@pytest.mark.parametrize(
    ('option', 'value', 'expected'),
    [
        pytest.param(WordsOption('words', ()), ['npm'], ('npm',), id='word list'),
        pytest.param(HeadingLevelsOption('levels', ()), [2, 3], (2, 3), id='heading levels'),
        pytest.param(CountOption('limit', 3), 5, 5, id='count'),
    ],
)
def test_an_option_converts_a_config_value_to_the_type_of_its_default(
    option: RuleOption[object], value: object, expected: object
) -> None:
    assert option.convert(value) == expected
