import pytest
from factories import document, found, lint, markdown, rule_ids
from factories import fixed as fix_document
from factories import rule_set as enabling

from subedit.domain import Document, RuleSet, RuleSettings, Severity
from subedit.domain.models.title_case import title_case
from subedit.infrastructure import MARKDOWN_RULES, WORDING_RULES


RULES = WORDING_RULES + MARKDOWN_RULES


def rule_set(**settings: RuleSettings) -> RuleSet:
    return enabling(rule_ids(RULES), settings=settings)


def ids(subject: Document, rules: RuleSet | None = None) -> list[str]:
    return found(lint(subject, rules or rule_set(), RULES))


def fixed(subject: Document, rules: RuleSet | None = None) -> str:
    return fix_document(subject, rules or rule_set(), RULES)


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
    assert 'mid-sentence-colon' in ids(document(f'def f():\n{comment}    pass\n'))


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
    assert 'mid-sentence-colon' not in ids(document(f'def f():\n{comment}    pass\n'))


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
    assert fixed(document('# 使用（全形括號）說明。\nx = 1\n')) == '# 使用 (全形括號) 說明。\nx = 1\n'


def test_the_inclusion_verb_is_rewritten() -> None:
    assert fixed(markdown('三種方式包括這些。\n')) == '三種方式包含這些。\n'
    assert fixed(document('# 三種方式包括這些。\nx = 1\n')) == '# 三種方式包含這些。\nx = 1\n'


def test_contrast_framing_is_advice_for_a_rewrite() -> None:
    report = lint(markdown('這不是問題，是設計。\n'), rule_set(), RULES)
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
    assert (
        fixed(document('# Lead:\n# - cache size: the limit\nx = 1\n')) == '# Lead:\n# - Cache Size: the limit\nx = 1\n'
    )


def test_a_docstring_label_is_bold_since_a_docstring_renders() -> None:
    source = 'def f():\n    """Resolve it.\n\n    - cache size: the limit\n    """\n'
    assert '- **Cache Size**: the limit' in fixed(document(source))


def test_a_heading_is_put_in_title_case() -> None:
    assert fixed(markdown('## getting started with the cli\n')) == '## Getting Started With the Cli\n'


@pytest.mark.parametrize(
    ('style', 'expected'),
    [
        ('apa', '## Reading Config From the Project, so Far\n'),
        ('chicago', '## Reading Config from the Project, So Far\n'),
    ],
)
def test_a_heading_follows_the_title_case_standard_the_project_names(style: str, expected: str) -> None:
    rules = rule_set(**{'heading-title-case': RuleSettings(options={'style': style})})
    assert fixed(markdown('## reading config from the project, so far\n'), rules) == expected


def test_a_list_label_follows_the_heading_standard() -> None:
    rules = rule_set(**{'heading-title-case': RuleSettings(options={'style': 'chicago'})})
    source = '# Title\n\nLead.\n\n- working with lists: a description\n'
    assert fixed(markdown(source), rules) == '# Title\n\nLead.\n\n- **Working with Lists**: a description\n'


@pytest.mark.parametrize('heading', ['## Set Up the Project\n', '## Set up the Project\n'])
def test_a_word_that_may_be_an_adverb_keeps_the_case_written(heading: str) -> None:
    assert fixed(markdown(heading)) == heading


@pytest.mark.parametrize('heading', ['## Cloud and On-Prem Pairing\n', '## A Pick-up Line\n'])
def test_a_minor_word_in_a_hyphenated_compound_keeps_its_case(heading: str) -> None:
    assert ids(markdown(heading)) == []


def test_a_capitalized_word_that_may_be_a_preposition_is_a_warning() -> None:
    report = lint(markdown('## Getting Started In Python\n'), rule_set(), RULES)
    (finding,) = [item for item in report.diagnostics if item.rule_id == 'heading-title-case']
    assert finding.severity is Severity.WARNING
    assert finding.message.startswith('In stays lowercase')


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


def noun_phrase_severities(source: str, rules: RuleSet | None = None) -> list[Severity]:
    report = lint(markdown(source), rules or rule_set(), RULES)
    return [item.severity for item in report.diagnostics if item.rule_id == 'heading-not-noun-phrase']


@pytest.mark.parametrize(
    'heading',
    ['## How to Install\n', '## When to Apply\n', '## Whose Config Wins\n', '## Is It Fast?\n', '## 設定在哪？\n'],
)
def test_a_question_heading_is_an_error(heading: str) -> None:
    assert noun_phrase_severities(heading) == [Severity.ERROR]


@pytest.mark.parametrize(
    'heading', ['## Use the Cache\n', '## Connect an MCP Server\n', '## 3. Configure Your Tools\n', '## Run It\n']
)
def test_a_verb_followed_by_its_object_is_an_instruction_and_a_warning(heading: str) -> None:
    assert noun_phrase_severities(heading) == [Severity.WARNING]


@pytest.mark.parametrize(
    'heading',
    [
        '## Installation\n',
        '## Getting Started\n',
        '## Bullet Points\n',
        '## Build Steps\n',
        '## Open Items\n',
        '## Install\n',
        '## For a Client\n',
        '## All the Rules\n',
        '## Proof That It Works\n',
        '## Reading the Config\n',
        '## Authority: the Oracle\n',
        '## Spine (Every Skill)\n',
    ],
)
def test_a_noun_heading_is_silent(heading: str) -> None:
    assert noun_phrase_severities(heading) == []


def test_heading_rules_read_only_the_levels_a_project_lists() -> None:
    levels = RuleSettings(options={'levels': (2, 3)})
    rules = rule_set(**{'heading-not-noun-phrase': levels, 'heading-title-case': levels})
    source = '# how subedit works\n\n## How It Works\n'
    assert ids(markdown(source), rules) == ['heading-not-noun-phrase']


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


def colon_severities(source: str, rules: RuleSet | None = None) -> list[Severity]:
    report = lint(markdown(source), rules or rule_set(), RULES)
    return [item.severity for item in report.diagnostics if item.rule_id == 'mid-sentence-colon']


@pytest.mark.parametrize(
    'item',
    [
        '- The write is idempotent: dates with an entry are skipped.',
        '- Can be empty: the field is optional.',
        '- Every test that runs before a deploy: the CI job.',
        '- **A label the author set in bold but let run on far too long**: a description.',
    ],
    ids=['clause', 'auxiliary', 'long', 'long bold'],
)
def test_words_in_a_labels_place_that_may_not_be_one_are_a_warning(item: str) -> None:
    assert colon_severities(f'# Title\n\nLead.\n\n{item}\n') == [Severity.WARNING]


@pytest.mark.parametrize(
    'source',
    [
        'The contract is fixed: implementations return headers.\n',
        '# Title\n\nLead.\n\n- **Label**: one clause ends here: and another starts.\n',
    ],
    ids=['paragraph', 'after a label'],
)
def test_a_colon_away_from_any_label_stays_an_error(source: str) -> None:
    assert colon_severities(source) == [Severity.ERROR]


def test_a_project_can_set_the_label_guess_back_to_an_error() -> None:
    rules = rule_set(**{'mid-sentence-colon': RuleSettings(severity=Severity.ERROR)})
    assert colon_severities('# Title\n\nLead.\n\n- Can be empty: the field is optional.\n', rules) == [Severity.ERROR]


def test_a_longer_label_limit_reaches_the_label_style_too() -> None:
    source = markdown('# Title\n\nLead.\n\n- every test before a deploy runs: the CI job.\n')
    rules = rule_set(**{'mid-sentence-colon': RuleSettings(options={'max-label-words': 6})})
    assert colon_severities('# Title\n\nLead.\n\n- every test before a deploy runs: the CI job.\n', rules) == []
    assert '- **Every Test Before a Deploy Runs**: the CI job.' in fixed(source, rules)


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
