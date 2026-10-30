import pytest
from factories import Project, document, found, lint, rule_set
from factories import fixed as fix_document

from subedit.domain import CommentGroup, CommentPlacement
from subedit.infrastructure import COMMENT_PARSER
from subedit.presentation.cli import app


def parse(source: str, language_id: str) -> tuple[CommentGroup, ...]:
    return COMMENT_PARSER.parse(document(source, language_id))


def fixed(source: str, language_id: str, width: int = 80) -> str:
    return fix_document(document(source, language_id), rule_set(width=width))


@pytest.mark.parametrize(
    ('source', 'expected', 'language_id'),
    [
        (
            'on:\n  # Only master, since a branch runs\n  # through its pull request.\n  push: [master]\n',
            'on:\n  # Only master, since a branch runs through its pull request.\n  push: [master]\n',
            'yaml',
        ),
        (
            '{\n  // Keep the width in step\n  // with Prettier.\n  "printWidth": 100\n}\n',
            '{\n  // Keep the width in step with Prettier.\n  "printWidth": 100\n}\n',
            'json',
        ),
    ],
)
def test_a_comment_broken_mid_clause_is_joined(source: str, expected: str, language_id: str) -> None:
    assert fixed(source, language_id) == expected


@pytest.mark.parametrize(
    ('source', 'language_id'),
    [
        (
            'jobs:\n  test:\n    # timeout-minutes: 30\n    # runs-on: macos-latest\n    runs-on: ubuntu-latest\n',
            'yaml',
        ),
        ('steps:\n  # - uses: actions/checkout@v4\n  #   with:\n  #     depth: 0\n  - run: make\n', 'yaml'),
        ('{\n  // "printWidth": 100,\n  // "semi": false,\n  "tabWidth": 2\n}\n', 'json'),
    ],
)
def test_a_setting_commented_out_is_code(source: str, language_id: str) -> None:
    assert fixed(source, language_id, width=20) == source


def test_a_label_closing_on_a_period_is_prose() -> None:
    group = parse('a:\n  # Note: this runs first.\n  b: 1\n', 'yaml')[0]
    assert group.prose().flattened == 'Note: this runs first.'


def test_a_note_at_the_top_of_a_data_file_is_no_file_header() -> None:
    source = '# Runs the tests on every push.\n\nname: CI\n'
    assert [group.placement for group in parse(source, 'yaml')] == [CommentPlacement.INLINE_BODY]
    assert 'file-header-comment' not in found(lint(document(source, 'yaml')))


def test_a_comment_a_tool_reads_is_no_prose() -> None:
    assert (
        parse('# yaml-language-server: $schema=https://json.schemastore.org/github-workflow.json\na: 1\n', 'yaml') == ()
    )


def test_a_block_comment_in_json_is_left_alone() -> None:
    assert parse('{\n  /* "semi": false */\n  "a": 1\n}\n', 'json') == ()


def test_a_trailing_comment_stays_beside_its_value() -> None:
    assert [group.placement for group in parse('a: 1  # seconds\n', 'yaml')] == [CommentPlacement.TRAILING]


@pytest.mark.parametrize('lock_file', ['package-lock.json', 'pnpm-lock.yaml'])
def test_check_walks_data_files_but_skips_what_a_tool_writes(
    project: Project, capsys: pytest.CaptureFixture[str], lock_file: str
) -> None:
    project.write('settings.json', '{\n  // Keep the width in step\n  // with Prettier.\n  "a": 1\n}\n')
    project.write(lock_file, '# Written by the package manager,\n# never by hand.\na: 1\n')

    with pytest.raises(SystemExit):
        app(['check', '--no-delegate', str(project.root)])
    output = capsys.readouterr().out
    assert 'settings.json' in output
    assert lock_file not in output
