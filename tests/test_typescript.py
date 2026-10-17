import pathlib

import pytest

from subedit.application import Linter, RuleEngine
from subedit.domain import CommentForm, CommentPlacement, Document, RuleSet, Visibility, apply_edits
from subedit.infrastructure import ALL_RULES, DEFAULT_CONFIG_SOURCE, DEFAULT_PARSER, LAYOUT_RULES, language_for
from subedit.presentation import hook
from subedit.presentation.cli import app


def parse(source: str, language_id: str = 'typescript'):
    return DEFAULT_PARSER.parse(Document(uri='file:///a.ts', text=source, language_id=language_id))


def lint(source: str, width: int = 80, rules=ALL_RULES):
    document = Document(uri='file:///a.ts', text=source, language_id='typescript')
    enabled = frozenset(rule.metadata.rule_id for rule in rules)
    return Linter(DEFAULT_PARSER, RuleEngine(rules)).run(document, RuleSet(enabled_rule_ids=enabled, line_width=width))


def ids(source: str, width: int = 80) -> list[str]:
    return [item.rule_id for item in lint(source, width).diagnostics]


def fixed(source: str, width: int = 80) -> str:
    report = lint(source, width, LAYOUT_RULES)
    edits = tuple(edit for item in report.mechanical if item.fix for edit in item.fix.edits)
    return apply_edits(source, edits[:1]) if edits else source


@pytest.mark.parametrize(
    ('name', 'language_id'),
    [('a.ts', 'typescript'), ('a.mts', 'typescript'), ('a.cts', 'typescript'), ('a.tsx', 'tsx'), ('a.js', None)],
)
def test_the_language_follows_the_extension(name: str, language_id: str | None) -> None:
    language = language_for(pathlib.Path(name))
    assert (language.language_id if language else None) == language_id


def test_line_comments_group_and_a_jsdoc_block_is_the_doc_form() -> None:
    source = '// first line,\n// second line.\nconst x = 1;\n\n/** Builds it. */\nexport function build() {}\n'
    groups = parse(source)
    assert [group.form for group in groups] == [CommentForm.LINE, CommentForm.DOC]
    assert groups[0].prose().flattened == 'first line, second line.'


def test_a_jsdoc_block_documents_the_declaration_below_it() -> None:
    groups = parse('/** Builds it. */\nexport function build() {}\n')
    assert groups[0].placement is CommentPlacement.LEADING_DECLARATION
    assert groups[0].attachment is not None
    assert groups[0].attachment.name == 'build'


def test_a_plain_block_comment_is_left_to_vale() -> None:
    assert parse('/* Copyright the authors. */\nexport const x = 1;\n') == ()


@pytest.mark.parametrize(
    'directive',
    [
        '/// <reference types="node" />',
        '// eslint-disable-next-line no-console',
        '// @ts-expect-error the value is wrong on purpose',
        '// prettier-ignore',
    ],
)
def test_a_directive_is_no_prose(directive: str) -> None:
    assert parse(f'function f() {{\n  {directive}\n  run();\n}}\n') == ()


@pytest.mark.parametrize(
    ('source', 'visibility'),
    [
        ('/** Doc. */\nexport function build() {}\n', Visibility.PUBLIC),
        ('/** Doc. */\nfunction build() {}\n', Visibility.INTERNAL),
        ('/** Doc. */\nexport const build = () => 1;\n', Visibility.PUBLIC),
        ('export class C {\n  /** Doc. */\n  render() {}\n}\n', Visibility.PUBLIC),
        ('export class C {\n  /** Doc. */\n  private count = 0;\n}\n', Visibility.INTERNAL),
        ('export class C {\n  /** Doc. */\n  protected helper() {}\n}\n', Visibility.INTERNAL),
        ('export class C {\n  /** Doc. */\n  #secret = 1;\n}\n', Visibility.INTERNAL),
        ('class C {\n  /** Doc. */\n  render() {}\n}\n', Visibility.INTERNAL),
        ('export interface I {\n  /** Doc. */\n  name: string;\n}\n', Visibility.PUBLIC),
        ('export function f() {\n  /** Doc. */\n  const local = 1;\n}\n', Visibility.INTERNAL),
    ],
)
def test_visibility_comes_from_export_and_modifiers(source: str, visibility: Visibility) -> None:
    attachment = parse(source)[0].attachment
    assert attachment is not None
    assert attachment.visibility is visibility


def test_a_plain_comment_on_an_exported_symbol_asks_for_jsdoc() -> None:
    report = lint('// Builds it.\nexport function build() {}\n')
    assert [item.rule_id for item in report.diagnostics] == ['plain-comment-on-public']
    assert '/**' in report.diagnostics[0].message


def test_a_plain_comment_on_an_internal_symbol_is_fine() -> None:
    assert ids('// Builds it.\nfunction build() {}\n') == []


def test_a_param_tag_restates_the_signature() -> None:
    source = '/**\n * Builds it.\n *\n * @param name the name\n */\nexport function build(name: string) {}\n'
    assert 'signature-restating-tag' in ids(source)


def test_a_jsdoc_block_keeps_its_frame_when_reflowed() -> None:
    source = (
        '/**\n'
        ' * Read a value from the store, falling back to the\n'
        ' * default when the key is missing.\n'
        ' */\n'
        'export function read() {}\n'
    )
    assert fixed(source, width=60) == (
        '/**\n'
        ' * Read a value from the store,\n'
        ' * falling back to the default when the key is missing.\n'
        ' */\n'
        'export function read() {}\n'
    )


def test_a_one_line_jsdoc_that_overflows_opens_into_a_frame() -> None:
    source = '  /** Read a value from the store, falling back to the default when the key is missing. */\n'
    assert fixed(f'class C {{\n{source}  read() {{}}\n}}\n', width=70) == (
        'class C {\n'
        '  /**\n'
        '   * Read a value from the store,\n'
        '   * falling back to the default when the key is missing.\n'
        '   */\n'
        '  read() {}\n'
        '}\n'
    )


def test_a_one_line_jsdoc_that_fits_stays_on_one_line() -> None:
    source = '/** Write a value. Then flush it. */\nexport function write() {}\n'
    assert fixed(source) == source, 'a doc block has no summary line, so no blank line lands after the first sentence'


def test_the_tag_section_and_an_example_are_left_as_written() -> None:
    source = (
        '/**\n'
        ' * Close the store.\n'
        ' *\n'
        ' * @throws when the lock\n'
        ' * is already gone.\n'
        ' * @example\n'
        ' * store.close(); store.open();\n'
        ' */\n'
        'export function close() {}\n'
    )
    assert fixed(source) == source


def test_an_example_holds_code_rather_than_prose() -> None:
    group = parse('/**\n * Close it.\n *\n * @example\n * store.close();\n */\nexport function close() {}\n')[0]
    assert len(group.code_ranges()) == 1


def test_a_typescript_file_defaults_to_the_prettier_width(tmp_path: pathlib.Path) -> None:
    assert DEFAULT_CONFIG_SOURCE.resolve(str(tmp_path / 'a.ts')).line_width == 80
    assert DEFAULT_CONFIG_SOURCE.resolve(str(tmp_path / 'a.py')).line_width == 120


def test_a_configured_width_applies_to_typescript_too(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'subedit.toml').write_text('[subedit]\nline-width = 100\n', encoding='utf-8')
    assert DEFAULT_CONFIG_SOURCE.resolve(str(tmp_path / 'a.ts')).line_width == 100


def test_check_walks_typescript_but_skips_node_modules(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for folder in ('src', 'node_modules/pkg'):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / 'a.ts').write_text('// Builds it.\nexport function build() {}\n', encoding='utf-8')

    with pytest.raises(SystemExit):
        app(['check', '--no-delegate', str(tmp_path)])
    output = capsys.readouterr().out
    assert 'src/a.ts' in output
    assert 'node_modules' not in output, 'installed packages hold code nobody here wrote'


def test_the_hook_repairs_a_typescript_edit(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'subedit.toml').write_text('[subedit]\nline-width = 74\n', encoding='utf-8')
    target = tmp_path / 'probe.ts'
    target.write_text(
        'function f() {\n'
        '  // cap the size to the shared limit so the mmap does not\n'
        '  // blow past it, an unbounded value faults the runner.\n'
        '  return 1;\n'
        '}\n',
        encoding='utf-8',
    )
    result = hook.run({'tool_name': 'Edit', 'tool_input': {'file_path': str(target)}})
    assert result.repaired_paths == (str(target),)
    assert '  // cap the size to the shared limit so the mmap does not blow past it,\n' in target.read_text(
        encoding='utf-8'
    )


def test_commented_out_code_is_not_joined_into_a_sentence() -> None:
    source = 'export class C {\n  // get count(): number {\n  //   return 1\n  // }\n  run() {}\n}\n'
    assert fixed(source) == source
