import pathlib

import pytest

from subedit.application import Linter, RuleEngine
from subedit.domain import Document, RuleSet
from subedit.infrastructure import ALL_RULES, DEFAULT_CONFIG_SOURCE, DEFAULT_PARSER, PYTHON


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / 'src'


def lint_text(text: str, rules: RuleSet | None = None):
    document = Document(uri='file:///probe.py', text=text, language_id=PYTHON.language_id)
    engine = RuleEngine(ALL_RULES)
    return Linter(DEFAULT_PARSER, engine).run(document, rules or DEFAULT_CONFIG_SOURCE.resolve(str(SOURCE_ROOT)))


def source_files() -> list[pathlib.Path]:
    return sorted(SOURCE_ROOT.rglob('*.py'))


def test_the_corpus_is_not_empty() -> None:
    assert len(source_files()) > 10


def test_the_project_carries_comments_worth_checking() -> None:
    blocks = 0
    for path in source_files():
        document = Document(
            uri=path.resolve().as_uri(),
            text=path.read_text(encoding='utf-8'),
            language_id=PYTHON.language_id,
        )
        blocks += len(DEFAULT_PARSER.parse(document))
    assert blocks > 0, 'a clean self-hosting run means nothing if there is nothing to check'


def test_subedit_lints_itself_clean() -> None:
    rules = DEFAULT_CONFIG_SOURCE.resolve(str(SOURCE_ROOT))
    engine = RuleEngine(ALL_RULES)
    linter = Linter(DEFAULT_PARSER, engine)

    findings: list[str] = []
    for path in source_files():
        document = Document(
            uri=path.resolve().as_uri(),
            text=path.read_text(encoding='utf-8'),
            language_id=PYTHON.language_id,
        )
        for item in linter.run(document, rules).diagnostics:
            findings.append(f'{path.relative_to(REPOSITORY_ROOT)}: {item.rule_id} {item.message[:80]}')
    assert not findings, f'{len(findings)} self-hosting findings: {findings[:5]}'


@pytest.mark.parametrize(
    ('probe', 'expected'),
    [
        (
            'def f():\n    # cap the size so the mmap does not\n    # blow past it, an unbounded value faults.\n    pass\n',
            'mid-clause-break',
        ),
        (
            'def f():\n    # this single sentence carries no comma at all and runs a very long way past any '
            'sensible budget that a reader would tolerate on one line.\n    pass\n',
            'unbreakable-sentence',
        ),
    ],
)
def test_the_self_hosting_check_has_teeth(probe: str, expected: str) -> None:
    rules = RuleSet(enabled_rule_ids=frozenset(rule.metadata.rule_id for rule in ALL_RULES), line_width=60)
    assert expected in [item.rule_id for item in lint_text(probe, rules).diagnostics]


def test_the_project_config_is_readable_and_enables_every_rule() -> None:
    rules = DEFAULT_CONFIG_SOURCE.resolve(str(SOURCE_ROOT))
    assert rules.enabled_rule_ids == frozenset(rule.metadata.rule_id for rule in ALL_RULES)
    assert rules.line_width == 120


def test_the_rule_reference_matches_each_rule() -> None:
    from subedit.infrastructure import ALL_RULES

    reference = (REPOSITORY_ROOT / 'docs' / 'rules.md').read_text(encoding='utf-8')
    rows = {
        cells[0].strip('`'): cells
        for line in reference.splitlines()
        if line.startswith('| `')
        for cells in [[cell.strip() for cell in line.strip('|').split('|')]]
    }
    for rule in ALL_RULES:
        metadata = rule.metadata
        assert metadata.rule_id in rows, f'{metadata.rule_id} is absent from docs/rules.md'
        _, _, fix_kind, level, _ = rows[metadata.rule_id]
        assert fix_kind.lower().startswith(metadata.fix_kind.value), f'{metadata.rule_id} fix kind is {fix_kind}'
        assert level == f'`{metadata.default_severity.name.lower()}`', f'{metadata.rule_id} level is {level}'


def test_the_rule_reference_lists_every_vale_rule() -> None:
    reference = (REPOSITORY_ROOT / 'docs' / 'rules.md').read_text(encoding='utf-8')
    styles = REPOSITORY_ROOT / 'src' / 'subedit' / 'vale' / 'styles' / 'subedit'
    missing = [path.stem for path in styles.glob('*.yml') if f'`subedit.{path.stem}`' not in reference]
    assert not missing, f'Vale rules absent from docs/rules.md: {missing}'


def test_the_repository_installs_its_own_hook() -> None:
    import json

    settings = json.loads((REPOSITORY_ROOT / '.claude' / 'settings.json').read_text(encoding='utf-8'))
    commands = [
        entry['command']
        for group in settings['hooks']['PostToolUse']
        for entry in group['hooks']
        if entry.get('type') == 'command'
    ]
    assert any('subedit-hook' in command for command in commands)


def test_the_excluded_fixture_is_actually_excluded() -> None:
    from subedit.infrastructure import DEFAULT_CONFIG_SOURCE

    fixture = REPOSITORY_ROOT / 'tests' / 'fixtures' / 'vale' / 'violations.py'
    patterns = DEFAULT_CONFIG_SOURCE.exclude_patterns(str(fixture))
    assert patterns, 'the project config must declare an exclude for deliberate fixtures'
    assert DEFAULT_CONFIG_SOURCE.is_excluded(fixture, REPOSITORY_ROOT, patterns)
    assert not DEFAULT_CONFIG_SOURCE.is_excluded(
        REPOSITORY_ROOT / 'src' / 'subedit' / 'domain' / 'prose.py', REPOSITORY_ROOT, patterns
    )
