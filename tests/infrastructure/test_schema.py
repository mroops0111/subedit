import re

import pytest

from subedit.domain import Severity
from subedit.infrastructure.config_sources import ConfigError, ConfigFile, RuleTable
from subedit.infrastructure.linters.vale_linter import ValeReport


def test_a_missing_section_falls_back_to_defaults() -> None:
    parsed = ConfigFile.parse({})
    assert parsed.subedit.line_width is None, 'an unset width falls back to the language default'
    assert parsed.subedit.exclude == ()
    assert parsed.rules == {}


def test_the_hyphenated_key_is_accepted() -> None:
    assert ConfigFile.parse({'subedit': {'line-width': 88}}).subedit.line_width == 88


@pytest.mark.parametrize('width', ['wide', 0, -10, [80]])
def test_a_nonsense_width_is_a_config_error(width: object) -> None:
    with pytest.raises(ConfigError, match=re.escape('subedit.line-width')):
        ConfigFile.parse({'subedit': {'line-width': width}})


def test_a_rule_entry_may_be_a_string_or_a_table() -> None:
    parsed = ConfigFile.parse(
        {'rules': {'a': 'off', 'b': 'warning', 'c': {'severity': 'error', 'minimum-characters': 30}}}
    )
    assert parsed.rules['a'] == 'off'
    assert parsed.rules['b'] == 'warning'
    table = parsed.rules['c']
    assert isinstance(table, RuleTable)
    assert table.resolved_severity is Severity.ERROR
    assert table.options == {'minimum-characters': 30}


def test_a_boolean_is_not_a_rule_entry() -> None:
    with pytest.raises(ConfigError, match=re.escape("rules.a: Input should be 'off'")):
        ConfigFile.parse({'rules': {'a': False}})


def test_extra_options_survive_on_a_rule_table() -> None:
    table = RuleTable.model_validate({'severity': 'warning', 'line': 4, 'doc-public': 17})
    assert table.options == {'line': 4, 'doc-public': 17}


def test_exclude_patterns_are_read() -> None:
    assert ConfigFile.parse({'subedit': {'exclude': ['a/**', 'b.py']}}).subedit.exclude == ('a/**', 'b.py')


def test_a_vale_report_decodes_alerts() -> None:
    payload = """
    {"a.py": [{"Check": "subedit.Semicolon", "Message": "no semicolons", "Line": 3,
               "Span": [10, 11], "Severity": "warning"}]}
    """
    alerts = ValeReport.parse(payload)
    assert len(alerts) == 1
    assert alerts[0].check == 'subedit.Semicolon'
    assert alerts[0].span == (10, 11)
    assert alerts[0].resolved_severity is Severity.WARNING


def test_a_vale_alert_defaults_its_span_and_severity() -> None:
    alerts = ValeReport.parse('{"a.py": [{"Check": "c", "Message": "m", "Line": 1}]}')
    assert alerts[0].span == (1, 1)
    assert alerts[0].resolved_severity is Severity.ERROR


@pytest.mark.parametrize(
    'payload',
    ['', 'not json', '[]', '{"a.py": "not a list"}', '{"a.py": [{"Check": "c"}]}', '{"a.py": [{"Line": 0}]}'],
)
def test_malformed_vale_output_yields_nothing_rather_than_raising(payload: str) -> None:
    assert ValeReport.parse(payload) == ()


def test_unknown_vale_fields_are_ignored() -> None:
    payload = '{"a.py": [{"Check": "c", "Message": "m", "Line": 1, "Description": "extra", "Link": "x"}]}'
    assert len(ValeReport.parse(payload)) == 1
