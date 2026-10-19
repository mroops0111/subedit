import pathlib

import pytest

from subedit.application import Linter, RuleEngine
from subedit.domain import CommentForm, CommentPlacement, Document, RuleSet, Visibility, apply_edits
from subedit.infrastructure import (
    ALL_RULES,
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_PARSER,
    LAYOUT_RULES,
    SUFFIX_ALIASES,
    TYPESCRIPT,
    language_for,
)
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
        ('/** Doc. */\nconst build = 1;\nexport { build };\n', Visibility.PUBLIC),
        ('/** Doc. */\nfunction build() {}\nexport default build;\n', Visibility.PUBLIC),
        ('/** Doc. */\nconst build = 1;\nexport { other };\n', Visibility.INTERNAL),
        ('/** Doc. */\ndeclare function build(): void;\n', Visibility.PUBLIC),
        ('/** Doc. */\n@Component({})\nexport class C {}\n', Visibility.PUBLIC),
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


def test_typescript_and_python_share_a_default_width(tmp_path: pathlib.Path) -> None:
    assert DEFAULT_CONFIG_SOURCE.resolve(str(tmp_path / 'a.ts')).line_width == 120
    assert DEFAULT_CONFIG_SOURCE.resolve(str(tmp_path / 'a.py')).line_width == 120


def test_a_configured_width_applies_to_typescript_too(tmp_path: pathlib.Path) -> None:
    (tmp_path / 'subedit.toml').write_text('[subedit]\nline-width = 100\n', encoding='utf-8')
    assert DEFAULT_CONFIG_SOURCE.resolve(str(tmp_path / 'a.ts')).line_width == 100


@pytest.mark.parametrize('vendored', ['node_modules/pkg', 'venv/lib', '.venv/lib'])
def test_check_walks_typescript_but_skips_installed_packages(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], vendored: str
) -> None:
    for folder in ('src', vendored):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / 'a.ts').write_text('// Builds it.\nexport function build() {}\n', encoding='utf-8')

    with pytest.raises(SystemExit):
        app(['check', '--no-delegate', str(tmp_path)])
    output = capsys.readouterr().out
    assert 'src/a.ts' in output
    assert vendored.split('/')[0] not in output, 'installed packages hold code nobody here wrote'


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


@pytest.mark.parametrize(
    'code',
    [
        '  // get count(): number {\n  //   return 1\n  // }\n',
        '  // function f(\n  //   params: string = {}\n  // )\n',
    ],
)
def test_commented_out_code_is_not_joined_into_a_sentence(code: str) -> None:
    source = f'export class C {{\n{code}  run() {{}}\n}}\n'
    assert fixed(source) == source


@pytest.mark.parametrize('export', ['export { C };', 'export default C;'])
def test_a_member_of_a_class_exported_later_is_public(export: str) -> None:
    attachment = parse(f'class C {{\n  /** Doc. */\n  run() {{}}\n}}\n{export}\n')[0].attachment
    assert attachment is not None
    assert attachment.visibility is Visibility.PUBLIC, 'the export names the class, and the member goes with it'


def test_the_exports_are_read_once_per_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    original = type(TYPESCRIPT).exported_names
    monkeypatch.setattr(
        type(TYPESCRIPT), 'exported_names', lambda self, root: calls.append(root) or original(self, root)
    )
    parse(''.join(f'/** Doc. */\nconst a{index} = 1;\n' for index in range(5)))
    assert len(calls) == 1


@pytest.mark.parametrize('overflow', [1, 4])
def test_a_one_line_jsdoc_just_over_the_width_opens_into_a_frame(overflow: int) -> None:
    text = 'Read a value from the store and hand it back to the caller'
    source = f'/** {text}{"x" * (80 - 7 - len(text) + overflow)} */\nexport function read() {{}}\n'
    repaired = fixed(source)
    assert repaired != source
    assert max(len(line) for line in repaired.splitlines()) <= 80


def test_a_one_line_jsdoc_that_fits_exactly_stays_on_one_line() -> None:
    text = 'Read a value.'
    source = f'/** {text}{"x" * (80 - 7 - len(text))} */\nexport function read() {{}}\n'
    assert fixed(source) == source


@pytest.mark.parametrize('tag', ['@typeParam T the element kind', '@typedef {object} Options', '@returnsDeep the copy'])
def test_a_tag_that_only_starts_like_a_signature_tag_is_fine(tag: str) -> None:
    source = f'/**\n * Builds it.\n *\n * {tag}\n */\nexport function build<T>() {{}}\n'
    assert 'signature-restating-tag' not in ids(source)


@pytest.mark.parametrize('tag', ['@returns the built thing', '@return the built thing', '@type {string}'])
def test_a_signature_tag_is_matched_as_a_whole_word(tag: str) -> None:
    source = f'/**\n * Builds it.\n *\n * {tag}\n */\nexport function build() {{}}\n'
    assert 'signature-restating-tag' in ids(source)


def test_an_inline_link_closing_a_jsdoc_line_is_prose() -> None:
    group = parse('/**\n * Read it, as described in\n * {@link Store}\n */\nexport function read() {}\n')[0]
    assert group.prose().flattened == 'Read it, as described in {@link Store}'
    assert group.code_ranges() == (), 'only a line that opens or closes a block of code is code'


def test_the_typescript_extensions_alias_to_the_one_prose_tools_know() -> None:
    assert SUFFIX_ALIASES == {'.mts': '.ts', '.cts': '.ts', '.pyi': '.py'}


def test_a_heading_over_several_fields_documents_none_of_them() -> None:
    source = (
        'export interface Services {\n'
        '  // Infrastructure singletons.\n'
        '  eventBus: EventBus;\n'
        '  clock: Clock;\n'
        '\n'
        '  // The registry, which plugins fill.\n'
        '  registry: Registry;\n'
        '}\n'
    )
    assert ids(source) == ['plain-comment-on-public'], 'only the comment over a single field documents it'
    assert lint(source).diagnostics[0].message.startswith('registry')


def test_a_trailing_comment_gets_one_finding_for_its_width() -> None:
    source = 'export function f() {\n  return new Promise(() => {}) // stall, as a killed process would, forever\n}\n'
    assert ids(source, width=60) == ['line-too-long']


def test_a_fix_never_pushes_a_wrapped_sentence_past_the_width() -> None:
    source = (
        '// NOTE: the earlier case is now blocked upstream by the scaffold check on\n'
        '// the source roles before the batch ever runs. It stays as a guard.\n'
        'export const x = 1;\n'
    )
    assert fixed(source) == source, 'joining the first sentence would run it to 113 characters'


@pytest.mark.parametrize(
    ('source', 'is_header'),
    [
        ("// Must stay first: it patches zod before any schema is built.\nimport './zod-openapi.js'\n", False),
        ("// The schema package.\nimport { z } from 'zod'\n", True),
    ],
)
def test_a_comment_over_an_import_run_for_its_effect_is_no_banner(source: str, is_header: bool) -> None:
    assert ('file-header-comment' in ids(source + '\nexport const x = 1;\n')) is is_header


@pytest.mark.parametrize(
    ('source', 'documented'),
    [
        (
            'export interface S {\n  clock: Clock;\n  // The bus every sync trigger uses.\n  bus: Bus;\n  log: Log;\n}\n',
            'bus',
        ),
        (
            "// Absent or 'human' is a person who logs in.\n"
            "export const UserKind = z.enum(['human']);\n"
            'export type UserKind = z.infer<typeof UserKind>;\n',
            'UserKind',
        ),
    ],
)
def test_a_comment_documents_the_one_declaration_under_it(source: str, documented: str) -> None:
    findings = lint(source).diagnostics
    assert [item.rule_id for item in findings] == ['plain-comment-on-public']
    assert findings[0].message.startswith(documented)
