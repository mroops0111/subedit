import pathlib

import pytest

from subedit.application import Fixer, Linter, RuleEngine
from subedit.domain import CommentGroup, Document, MarkdownBlock, MarkdownBlockKind, RuleSet
from subedit.infrastructure import ALL_RULES, DEFAULT_PARSER, MARKDOWN_RULES, MarkdownParser, language_id_for


def document(source: str) -> Document:
    return Document(uri='file:///notes.md', text=source, language_id='markdown')


def blocks(source: str) -> tuple[MarkdownBlock, ...]:
    return MarkdownParser().parse(document(source))


def rule_set() -> RuleSet:
    return RuleSet(enabled_rule_ids=frozenset(rule.metadata.rule_id for rule in ALL_RULES))


def ids(source: str) -> list[str]:
    report = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)).run(document(source), rule_set())
    return [diagnostic.rule_id for diagnostic in report.diagnostics]


def fixed(source: str) -> str:
    return Fixer(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES))).run(document(source), rule_set()).document.text


def test_markdown_files_are_read_as_markdown() -> None:
    assert language_id_for(pathlib.Path('README.md')) == 'markdown'
    assert language_id_for(pathlib.Path('notes.markdown')) == 'markdown'
    assert language_id_for(pathlib.Path('a.py')) == 'python'
    assert language_id_for(pathlib.Path('notes.txt')) is None


def test_headings_and_paragraphs_are_blocks_with_their_level() -> None:
    parsed = blocks('# Title\n\nA paragraph.\n\nSub\n---\n')
    assert [(block.kind, block.level, block.text) for block in parsed] == [
        (MarkdownBlockKind.HEADING, 1, 'Title'),
        (MarkdownBlockKind.PARAGRAPH, 0, 'A paragraph.'),
        (MarkdownBlockKind.HEADING, 2, 'Sub'),
    ]


def test_code_tables_html_and_front_matter_hold_no_blocks() -> None:
    source = (
        '---\ntitle: a\n---\n\n'
        '```python\nx = 1\n```\n\n'
        '    indented code\n\n'
        '| a | b |\n| --- | --- |\n| 1 | 2 |\n\n'
        '<div>\nhtml\n</div>\n'
    )
    assert blocks(source) == ()


def test_a_list_item_records_its_depth() -> None:
    parsed = blocks('- one\n  - two\n')
    assert [(block.text, block.list_depth) for block in parsed] == [('one', 1), ('two', 2)]


def test_a_continuation_line_keeps_its_indent_apart_from_its_text() -> None:
    (item,) = blocks('- item one\n  continues here\n')
    assert [(line.prefix, line.text) for line in item.lines] == [('', 'item one'), ('  ', 'continues here')]


def test_a_quoted_line_keeps_its_marker_apart_from_its_text() -> None:
    (quote,) = blocks('> quote line\n> more\n')
    assert [(line.prefix, line.text) for line in quote.lines] == [('', 'quote line'), ('> ', 'more')]


def test_every_block_comes_from_the_markdown_parser_and_no_comment_group_does() -> None:
    parsed = DEFAULT_PARSER.parse(document('# Title\n\nText.\n'))
    assert parsed
    assert not any(isinstance(unit, CommentGroup) for unit in parsed)


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('MCP has three transports,\neach with its use.\n', 'MCP has three transports, each with its use.\n'),
        ('MCP 目前有三種溝通方式，\n各有適用情境。\n', 'MCP 目前有三種溝通方式，各有適用情境。\n'),  # noqa: RUF001
        ('中文\n內容\n', '中文內容\n'),
        ('使用\nMCP 協定\n', '使用 MCP 協定\n'),
        ('- item one\n  continues here\n', '- item one continues here\n'),
        ('> quote line\n> more\n', '> quote line more\n'),
        ('trailing   \nspaces\n', 'trailing   \nspaces\n'),
    ],
)
def test_a_broken_paragraph_is_joined_into_one_line(source: str, expected: str) -> None:
    assert fixed(source) == expected


def test_a_hard_break_stays_while_the_soft_ones_close_up() -> None:
    source = 'First line  \nsecond part\nof it. Back\\\nslash.\n'
    assert fixed(source) == 'First line  \nsecond part of it. Back\\\nslash.\n'


def test_a_paragraph_on_one_line_is_clean() -> None:
    assert ids('# Title\n\nOne line paragraph, however long it runs.\n') == []


def test_a_broken_paragraph_is_reported() -> None:
    assert ids('A paragraph\nbroken in two.\n') == ['paragraph-line-break']


def test_code_is_never_joined() -> None:
    source = '```\nline one\nline two\n```\n'
    assert ids(source) == []
    assert fixed(source) == source


def test_a_heading_wrapped_in_bold_loses_the_markers() -> None:
    assert ids('# **Overview**\n') == ['heading-wrapped-in-bold']
    assert fixed('# **Overview**\n\n## __Detail__\n') == '# Overview\n\n## Detail\n'


@pytest.mark.parametrize('heading', ['# **Bold** and Plain\n', '# A **Bold** Word\n', '# **One** and **Two**\n'])
def test_a_heading_with_only_part_in_bold_is_left_alone(heading: str) -> None:
    assert ids(heading) == []


def test_bold_in_a_paragraph_is_no_heading_finding() -> None:
    assert ids('**Overview**\n') == []


def test_comment_rules_never_read_markdown() -> None:
    long_line = 'word ' * 60
    assert ids(f'{long_line.strip()}\n') == []


def test_markdown_rules_never_read_comments() -> None:
    source = '# A comment\n# broken in two.\nx = 1\n'
    report = Linter(DEFAULT_PARSER, RuleEngine(MARKDOWN_RULES)).run(
        Document(uri='file:///a.py', text=source, language_id='python'),
        RuleSet(enabled_rule_ids=frozenset(rule.metadata.rule_id for rule in MARKDOWN_RULES)),
    )
    assert report.is_clean


def test_an_outside_checker_may_edit_prose_but_not_code() -> None:
    inspection = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)).inspect(
        document('Prose here.\n\n```\ncode\n```\n'), rule_set()
    )
    assert len(inspection.prose_map.editable) == 1


def test_front_matter_code_and_tables_count_as_code_to_an_outside_checker() -> None:
    source = '---\ntitle: a\n---\n\nProse.\n\n```\ncode\n```\n\n| a |\n| --- |\n| 1 |\n'
    inspection = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)).inspect(document(source), rule_set())
    covered = [source.encode()[region.start : region.end].decode() for region in inspection.prose_map.code]
    assert covered == ['---\ntitle: a\n---\n', '```\ncode\n```\n', '| a |\n| --- |\n| 1 |\n']
