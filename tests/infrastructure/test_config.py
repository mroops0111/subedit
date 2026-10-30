import pathlib

import pytest
from factories import Project

from subedit.domain import Severity
from subedit.infrastructure import CONFIG_NAME, DEFAULT_CONFIG_SOURCE, TomlConfigSource


AVAILABLE = ('mid-clause-break', 'line-too-long', 'stub-fragment')


def source() -> TomlConfigSource:
    return TomlConfigSource(AVAILABLE)


def configured(project: Project, body: str, config: str = CONFIG_NAME) -> pathlib.Path:
    """A module in a repository whose config holds the body, which is the path a source resolves its rules for."""
    project.write(config, body)
    return project.write('module.py', '# note\n')


def test_defaults_enable_every_available_rule(tmp_path: pathlib.Path) -> None:
    rules = source().resolve(str(tmp_path))
    assert rules.enabled_rule_ids == frozenset(AVAILABLE)
    assert rules.line_width == 120


def test_configuration_is_found_by_walking_upward(project: Project) -> None:
    nested = project.root / 'a' / 'b'
    nested.mkdir(parents=True)
    configured(project, '[subedit]\nline-width = 88\n')
    assert source().resolve(str(nested / 'module.py')).line_width == 88


def test_a_rule_can_be_switched_off(project: Project) -> None:
    target = configured(project, '[rules]\nmid-clause-break = "off"\n')
    rules = source().resolve(str(target))
    assert not rules.is_enabled('mid-clause-break')
    assert rules.is_enabled('line-too-long')


def test_a_severity_string_is_honoured(project: Project) -> None:
    target = configured(project, '[rules]\nmid-clause-break = "warning"\n')
    rules = source().resolve(str(target))
    assert rules.settings_for('mid-clause-break').severity is Severity.WARNING


def test_a_table_carries_severity_and_options(project: Project) -> None:
    target = configured(project, '[rules]\nstub-fragment = { severity = "warning", minimum_characters = 30 }\n')
    settings = source().resolve(str(target)).settings_for('stub-fragment')
    assert settings.severity is Severity.WARNING
    assert settings.integer('minimum_characters', 24) == 30


def test_an_unknown_rule_leaves_the_native_rules_alone(project: Project) -> None:
    target = configured(project, '[rules]\nnot-a-rule = "off"\n')
    assert source().resolve(str(target)).enabled_rule_ids == frozenset(AVAILABLE)


def test_a_delegated_rule_can_be_tuned_or_switched_off(project: Project) -> None:
    target = configured(project, '[rules]\n"subedit.EmDash" = "warning"\n"subedit.DateRef" = "off"\n')
    rules = source().resolve(str(target))
    assert rules.settings_for('subedit.EmDash').severity is Severity.WARNING
    assert not rules.allows_external('subedit.DateRef')
    assert rules.allows_external('subedit.Semicolon')


def test_a_nonsense_width_falls_back_to_the_default(project: Project) -> None:
    target = configured(project, '[subedit]\nline-width = "wide"\n')
    assert source().resolve(str(target)).line_width == 120


PYPROJECT = 'pyproject.toml'


def test_settings_are_read_from_pyproject(project: Project) -> None:
    target = configured(project, '[project]\nname = "x"\n\n[tool.subedit]\nline-width = 96\n', PYPROJECT)
    assert source().resolve(str(target)).line_width == 96


def test_rules_nest_under_the_tool_table_in_pyproject(project: Project) -> None:
    body = '[tool.subedit]\nline-width = 96\n\n[tool.subedit.rules]\nmid-clause-break = "off"\n'
    rules = source().resolve(str(configured(project, body, PYPROJECT)))

    assert not rules.is_enabled('mid-clause-break')
    assert rules.is_enabled('line-too-long')


def test_excludes_are_read_from_pyproject(project: Project) -> None:
    body = '[tool.subedit]\nexclude = ["build/**"]\n'
    assert source().exclude_patterns(str(configured(project, body, PYPROJECT))) == ('build/**',)


def test_a_pyproject_without_our_table_is_ignored(project: Project) -> None:
    target = configured(project, '[project]\nname = "x"\n\n[tool.ruff]\nline-length = 88\n', PYPROJECT)
    assert source().resolve(str(target)).line_width == 120


def test_a_dedicated_file_wins_over_pyproject(project: Project) -> None:
    project.write(PYPROJECT, '[tool.subedit]\nline-width = 96\n')
    target = configured(project, '[subedit]\nline-width = 70\n')
    assert source().resolve(str(target)).line_width == 70


@pytest.mark.parametrize(
    ('file_name', 'body', 'suffix', 'width'),
    [
        ('pyproject.toml', '[tool.ruff]\nline-length = 88\n', '.py', 88),
        ('pyproject.toml', '[tool.black]\nline-length = 100\n', '.py', 100),
        ('ruff.toml', 'line-length = 79\n', '.py', 79),
        ('.prettierrc', '{ "printWidth": 100 }\n', '.ts', 100),
        ('.prettierrc', 'printWidth: 90\nsemi: false\n', '.ts', 90),
        ('.prettierrc.toml', 'printWidth = 110\n', '.tsx', 110),
        ('package.json', '{ "name": "a", "prettier": { "printWidth": 96 } }\n', '.ts', 96),
        (
            'biome.jsonc',
            '{\n  // the schema keeps its URL\n  "$schema": "https://biomejs.dev/schema.json",\n'
            '  "formatter": { "lineWidth": 100, },\n}\n',
            '.ts',
            100,
        ),
    ],
)
def test_the_width_follows_the_project_formatter(
    project: Project, file_name: str, body: str, suffix: str, width: int
) -> None:
    project.write(file_name, body)
    assert DEFAULT_CONFIG_SOURCE.resolve(str(project.root / 'src' / f'a{suffix}')).line_width == width


def test_one_language_formatter_leaves_the_other_language_alone(project: Project) -> None:
    project.write('.prettierrc', '{ "printWidth": 80 }\n')
    assert DEFAULT_CONFIG_SOURCE.resolve(str(project.root / 'a.py')).line_width == 120


def test_a_formatter_left_at_its_default_sets_no_width(project: Project) -> None:
    project.write('pyproject.toml', '[tool.ruff]\ntarget-version = "py311"\n')
    assert DEFAULT_CONFIG_SOURCE.resolve(str(project.root / 'a.py')).line_width == 120


def test_subedit_config_sets_the_width_over_the_formatter(project: Project) -> None:
    project.write('pyproject.toml', '[tool.ruff]\nline-length = 88\n\n[tool.subedit]\nline-width = 100\n')
    assert DEFAULT_CONFIG_SOURCE.resolve(str(project.root / 'a.py')).line_width == 100
