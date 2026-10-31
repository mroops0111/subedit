import dataclasses
import pathlib

import pytest
from factories import REPOSITORY_ROOT, document, found, lint, markdown, rule_ids, rule_set
from factories import fixed as fix_document

from subedit.application import Linter, RuleEngine
from subedit.domain import CommentGroup, MarkdownBlock, MarkdownBlockKind, RuleSet
from subedit.infrastructure import (
    ALL_RULES,
    DEFAULT_PARSER,
    MARKDOWN_RULES,
    AutoCorrectLinter,
    MarkdownParser,
    language_id_for,
)


def blocks(source: str) -> tuple[MarkdownBlock, ...]:
    return MarkdownParser().parse(markdown(source))


def ids(source: str) -> list[str]:
    return found(lint(markdown(source)))


def fixed(source: str) -> str:
    return fix_document(markdown(source))


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
    parsed = DEFAULT_PARSER.parse(markdown('# Title\n\nText.\n'))
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
    report = lint(document(source), rule_set(rule_ids(MARKDOWN_RULES)), MARKDOWN_RULES)
    assert report.is_clean


def test_an_outside_checker_may_edit_prose_but_not_code() -> None:
    inspection = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)).inspect(
        markdown('Prose here.\n\n```\ncode\n```\n'), rule_set()
    )
    assert len(inspection.prose_map.editable) == 1


def test_front_matter_code_and_tables_count_as_code_to_an_outside_checker() -> None:
    source = '---\ntitle: a\n---\n\nProse.\n\n```\ncode\n```\n\n| a |\n| --- |\n| 1 |\n'
    inspection = Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)).inspect(markdown(source), rule_set())
    covered = [source.encode()[region.start : region.end].decode() for region in inspection.prose_map.code]
    assert covered == ['---\ntitle: a\n---\n', '```\ncode\n```\n', '| a |\n| --- |\n| 1 |\n']


MIS_WRAPPED = '# cap the size so the mmap does not\n# blow past it, an unbounded value faults.\n'
REFLOWED = '# cap the size so the mmap does not blow past it,\n# an unbounded value faults.\n'


def code_blocks(width: int = 60) -> RuleSet:
    return dataclasses.replace(rule_set(width=width), reads_embedded=True)


def test_a_code_block_is_left_alone_unless_the_project_opts_in() -> None:
    source = f'Notes.\n\n```python\n{MIS_WRAPPED}```\n'
    assert 'mid-clause-break' not in found(lint(markdown(source), rule_set(width=60)))
    assert 'mid-clause-break' in found(lint(markdown(source), code_blocks()))


@pytest.mark.parametrize(
    ('block', 'expected'),
    [
        (f'```python\n{MIS_WRAPPED}```\n', f'```python\n{REFLOWED}```\n'),
        (
            '- Item.\n\n  ```py\n' + ''.join(f'  {line}\n' for line in MIS_WRAPPED.splitlines()) + '  ```\n',
            '- Item.\n\n  ```py\n' + ''.join(f'  {line}\n' for line in REFLOWED.splitlines()) + '  ```\n',
        ),
        (
            '> ```python\n' + ''.join(f'> {line}\n' for line in MIS_WRAPPED.splitlines()) + '> ```\n',
            '> ```python\n' + ''.join(f'> {line}\n' for line in REFLOWED.splitlines()) + '> ```\n',
        ),
        (f'```yaml\n{MIS_WRAPPED}key: 1\n```\n', f'```yaml\n{REFLOWED}key: 1\n```\n'),
    ],
    ids=['at the top level', 'in a list item', 'in a block quote', 'in YAML'],
)
def test_a_fix_in_a_code_block_keeps_what_sets_its_lines_apart(block: str, expected: str) -> None:
    source = f'Notes.\n\n{block}'
    assert fix_document(markdown(source), code_blocks()) == f'Notes.\n\n{expected}'


def test_a_code_block_is_a_fragment_so_no_comment_in_it_heads_a_file() -> None:
    source = 'Notes.\n\n```python\n# Install, then import the client.\nimport subedit\n```\n'
    assert found(lint(markdown(source), code_blocks())) == []


def test_a_checker_reads_a_code_block_as_its_own_language() -> None:
    source = 'Notes.\n\n- Item.\n\n  ```python\n  # 中文English\n  ```\n'
    checkers = (AutoCorrectLinter(),)
    assert 'autocorrect.Spacing' in found(lint(markdown(source), code_blocks(), checkers=checkers))
    assert fix_document(markdown(source), code_blocks(), checkers=checkers) == source.replace(
        '中文English', '中文 English'
    )


def test_a_block_in_a_language_subedit_does_not_read_is_left_alone() -> None:
    source = f'Notes.\n\n```ruby\n{MIS_WRAPPED}```\n'
    assert found(lint(markdown(source), code_blocks())) == []


@pytest.mark.parametrize(
    ('name', 'language_id'),
    [
        ('python', 'python'),
        ('py', 'python'),
        ('TS', 'typescript'),
        ('js', 'javascript'),
        ('yml', 'yaml'),
        ('jsonc', 'json'),
        ('text', None),
    ],
)
def test_an_info_string_names_a_language_by_its_id_or_its_extension(name: str, language_id: str | None) -> None:
    file_type = DEFAULT_PARSER.file_type_named(name)
    assert (file_type.language_id if file_type else None) == language_id


def test_reading_every_code_block_of_a_long_document_holds_up() -> None:
    # Walking the tokens inside a TOML block's content once crashed the tree-sitter binding partway through this file.
    readme = (REPOSITORY_ROOT / 'README.md').read_text(encoding='utf-8')
    assert lint(markdown(readme), code_blocks(width=120)).diagnostics is not None


def test_a_markdown_block_inside_markdown_is_an_example_left_alone() -> None:
    source = 'Notes.\n\n```markdown\n## lowercase heading\n\nA paragraph\nbroken by hand.\n```\n'
    assert found(lint(markdown(source), code_blocks())) == []
