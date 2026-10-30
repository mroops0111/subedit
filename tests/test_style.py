import pytest

from subedit.application import Fixer, Linter, RuleEngine
from subedit.domain import Document, RuleSet, RuleSettings
from subedit.domain.models.title_case import title_case
from subedit.infrastructure import DEFAULT_PARSER, MARKDOWN_RULES, WORDING_RULES


RULES = WORDING_RULES + MARKDOWN_RULES


def rule_set(**settings: RuleSettings) -> RuleSet:
    return RuleSet(enabled_rule_ids=frozenset(rule.metadata.rule_id for rule in RULES), settings=settings)


def markdown(source: str) -> Document:
    return Document(uri='file:///notes.md', text=source, language_id='markdown')


def python(source: str) -> Document:
    return Document(uri='file:///a.py', text=source, language_id='python')


def ids(document: Document, rules: RuleSet | None = None) -> list[str]:
    report = Linter(DEFAULT_PARSER, RuleEngine(RULES)).run(document, rules or rule_set())
    return [diagnostic.rule_id for diagnostic in report.diagnostics]


def fixed(document: Document, rules: RuleSet | None = None) -> str:
    return Fixer(Linter(DEFAULT_PARSER, RuleEngine(RULES))).run(document, rules or rule_set()).document.text


@pytest.mark.parametrize(
    'source',
    [
        'The contract is fixed: implementations return headers.\n',
        '中文句子有冒號：然後繼續說明。\n',
        'Three modes exist: stdio, SSE, and HTTP.\n',
    ],
)
def test_a_colon_joining_clauses_in_markdown_is_flagged(source: str) -> None:
    assert ids(markdown(source)) == ['mid-sentence-colon']


@pytest.mark.parametrize(
    'source',
    [
        '# Title\n\nLead.\n\n- **Bullet Label**: a description\n- **Label:** a description\n- 標籤：說明\n',
        '## Task: Do Something\n',
        'The order is fixed:\n\n- detect\n- pick\n',
        'A `TODO:` prefix and https://example.com are not colons in prose.\n',
        'The time is 10:30, and "Note: this" is quoted.\n',
        '> Quoted: words; kept as written.\n',
    ],
)
def test_a_colon_in_an_allowed_place_in_markdown_is_silent(source: str) -> None:
    assert 'mid-sentence-colon' not in ids(markdown(source))


@pytest.mark.parametrize(
    'comment',
    [
        '    """The contract is header-shaped, not value-shaped:\n    implementations return headers.\n    """\n',
        '    """The contract is header-shaped, not value-shaped: implementations return headers."""\n',
        '    # 這個設定有一個限制：不能超過十個。\n',
    ],
)
def test_a_colon_joining_clauses_in_a_comment_is_flagged(comment: str) -> None:
    assert 'mid-sentence-colon' in ids(python(f'def f():\n{comment}    pass\n'))


@pytest.mark.parametrize(
    'comment',
    [
        '    """Resolve auth.\n\n    The order is fixed:\n    - detect\n    - pick\n    """\n',
        '    """Resolve auth.\n\n    Run it like this:\n        subedit fix\n    """\n',
        '    """Resolve auth.\n\n    Two steps follow:\n\n    Detect, then pick.\n    """\n',
        '    """Resolve auth.\n\n    - Name: the value it takes\n    """\n',
        '    # Note: the cache is shared.\n',
    ],
)
def test_a_colon_in_an_allowed_place_in_a_comment_is_silent(comment: str) -> None:
    assert 'mid-sentence-colon' not in ids(python(f'def f():\n{comment}    pass\n'))


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('使用（全形括號）說明。\n', '使用 (全形括號) 說明。\n'),
        ('Heptabase(一個筆記工具)提供白板功能。\n', 'Heptabase (一個筆記工具) 提供白板功能。\n'),
        ('Heptabase ( 一個筆記工具 ) 提供白板功能。\n', 'Heptabase (一個筆記工具) 提供白板功能。\n'),
        ('A tool(over stdin) runs.\n', 'A tool (over stdin) runs.\n'),
        ('It ends here (as noted).\n', 'It ends here (as noted).\n'),
    ],
)
def test_parentheses_are_half_width_and_spaced(source: str, expected: str) -> None:
    assert fixed(markdown(source)) == expected


@pytest.mark.parametrize(
    'source', ['Call foo(bar) first.\n', 'See [the docs](https://example.com/a b).\n', 'Run `f( x )` once.\n']
)
def test_code_and_links_keep_their_parentheses(source: str) -> None:
    assert 'parenthesis-style' not in ids(markdown(source))


def test_a_comment_follows_the_parenthesis_style_too() -> None:
    assert fixed(python('# 使用（全形括號）說明。\nx = 1\n')) == '# 使用 (全形括號) 說明。\nx = 1\n'


def test_the_inclusion_verb_is_rewritten() -> None:
    assert fixed(markdown('三種方式包括這些。\n')) == '三種方式包含這些。\n'
    assert fixed(python('# 三種方式包括這些。\nx = 1\n')) == '# 三種方式包含這些。\nx = 1\n'


def test_contrast_framing_is_advice_for_a_rewrite() -> None:
    report = Linter(DEFAULT_PARSER, RuleEngine(RULES)).run(markdown('這不是問題，是設計。\n'), rule_set())
    [finding] = report.diagnostics
    assert finding.rule_id == 'contrast-framing'
    assert not finding.is_mechanical


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (
            '# Title\n\nLead.\n\n- bullet label: a description\n',
            '# Title\n\nLead.\n\n- **Bullet Label**: a description\n',
        ),
        ('# Title\n\nLead.\n\n- **bullet label:** text\n', '# Title\n\nLead.\n\n- **Bullet Label**: text\n'),
        ('# Title\n\nLead.\n\n- **Fine Label**: text\n', '# Title\n\nLead.\n\n- **Fine Label**: text\n'),
    ],
)
def test_a_markdown_label_is_bold_and_in_title_case(source: str, expected: str) -> None:
    assert fixed(markdown(source)) == expected


def test_a_line_comment_label_takes_title_case_but_no_bold() -> None:
    assert fixed(python('# Lead:\n# - cache size: the limit\nx = 1\n')) == '# Lead:\n# - Cache Size: the limit\nx = 1\n'


def test_a_docstring_label_is_bold_since_a_docstring_renders() -> None:
    source = 'def f():\n    """Resolve it.\n\n    - cache size: the limit\n    """\n'
    assert '- **Cache Size**: the limit' in fixed(python(source))


def test_a_heading_is_put_in_title_case() -> None:
    assert fixed(markdown('## getting started with the cli\n')) == '## Getting Started With the Cli\n'


def test_a_name_listed_under_keep_stays_lowercase() -> None:
    rules = rule_set(**{'heading-title-case': RuleSettings(options={'keep': ['uv', 'CLI']})})
    assert fixed(markdown('## install uv and the cli\n'), rules) == '## Install uv and the CLI\n'


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('model context protocol (MCP，模型上下文協定)', 'Model Context Protocol (MCP，模型上下文協定)'),
        ('an OAuth flow in iOS', 'An OAuth Flow in iOS'),
        ('`subedit fix` and its options', '`subedit fix` and Its Options'),
        ('settings in pyproject.toml', 'Settings in pyproject.toml'),
        ('task: do something', 'Task: Do Something'),
        ('what it is for', 'What It Is For'),
    ],
)
def test_title_case_leaves_code_names_and_acronyms_alone(text: str, expected: str) -> None:
    assert title_case(text) == expected


def test_a_heading_straight_into_a_list_needs_a_lead_sentence() -> None:
    assert 'missing-lead-sentence' in ids(markdown('## Transport\n\n- stdio\n- SSE\n'))
    assert 'missing-lead-sentence' not in ids(markdown('## Transport\n\nThere are two.\n\n- stdio\n- SSE\n'))


@pytest.mark.parametrize(
    'heading', ['## How to Install\n', '## When to Apply\n', '## Use the Cache\n', '## Is It Fast?\n']
)
def test_a_question_or_an_instruction_is_no_noun_heading(heading: str) -> None:
    assert 'heading-not-noun-phrase' in ids(markdown(heading))


@pytest.mark.parametrize('heading', ['## Installation\n', '## Getting Started\n', '## Bullet Points\n'])
def test_a_noun_heading_is_silent(heading: str) -> None:
    assert 'heading-not-noun-phrase' not in ids(markdown(heading))


@pytest.mark.parametrize(
    'item',
    [
        '- **Attendance** (`chr.example.com`, B4.1): per day records\n',
        '- `${DIR}/scripts/attendance.js` tab: the fetch call\n',
        '- **Root**: `~/work`\n',
    ],
)
def test_a_label_may_hold_code_or_a_parenthetical(item: str) -> None:
    assert 'mid-sentence-colon' not in ids(markdown(f'# Title\n\nLead.\n\n{item}'))


def test_a_clause_before_a_colon_is_no_label() -> None:
    found = ids(markdown('# Title\n\nLead.\n\n- The write is idempotent: dates with an entry are skipped.\n'))
    assert 'mid-sentence-colon' in found
    assert 'bullet-label-style' not in found


def test_a_label_keeps_its_parenthetical_when_styled() -> None:
    source = '# Title\n\nLead.\n\n- bucket a (gateway): mounts each API\n'
    assert fixed(markdown(source)) == '# Title\n\nLead.\n\n- **Bucket A** (gateway): mounts each API\n'


@pytest.mark.parametrize(
    'source',
    [
        '[![License: MIT](https://img.shields.io/badge/a.svg)](LICENSE)\n',
        '# Title\n\nLead.\n\n- **graph.png**: the model in Studio\n',
        '# Title\n\nLead.\n\n- **Field-level disagreement on a shared identity** (two sources): ask\n',
        '**Good example:**\n\n```\ncode\n```\n',
    ],
)
def test_a_badge_a_file_label_a_bold_label_and_a_bold_lead_in_are_allowed(source: str) -> None:
    assert 'mid-sentence-colon' not in ids(markdown(source))


@pytest.mark.parametrize('text', ['@braidhq/agent-claude-code', 'conciergent', 'orphaned'])
def test_a_name_or_a_lone_lowercase_word_keeps_its_case(text: str) -> None:
    assert title_case(text) == text


def test_a_lone_lowercase_label_gets_bold_but_keeps_its_case() -> None:
    assert (
        fixed(markdown('# Title\n\nLead.\n\n- skills: the prompts\n'))
        == '# Title\n\nLead.\n\n- **skills**: the prompts\n'
    )


def test_a_bare_www_address_is_stepped_over_like_any_url() -> None:
    assert 'parenthesis-style' not in ids(markdown('Open www.example.com/a(b c) to see it.\n'))


def test_parentheses_around_korean_are_an_aside_rather_than_a_call() -> None:
    assert fixed(markdown('이 설명(한국어)은 짧다.\n')) == '이 설명 (한국어) 은 짧다.\n'
