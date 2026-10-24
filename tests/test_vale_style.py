import pathlib
import shutil
import subprocess

import pytest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPOSITORY_ROOT / '.vale.ini'
FIXTURES = REPOSITORY_ROOT / 'tests' / 'fixtures' / 'vale'

EXPECTED_RULES = [
    'SignatureTag',
    'EmDash',
    'EditHistory',
    'ExternalRef',
    'Semicolon',
    'DateRef',
]

pytestmark = pytest.mark.skipif(shutil.which('vale') is None, reason='vale is not installed')


def run_vale(*targets: str) -> str:
    result = subprocess.run(
        ['vale', '--no-exit', '--output=line', f'--config={CONFIG}', *targets],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_every_rule_fires_on_the_violation_fixture(tmp_path: pathlib.Path) -> None:
    staged = tmp_path / 'violations.py'
    staged.write_text((FIXTURES / 'violations.py').read_text(encoding='utf-8'), encoding='utf-8')
    output = run_vale(str(staged))
    missing = [rule for rule in EXPECTED_RULES if rule not in output]
    assert not missing, f'rules that failed to fire: {missing}'


def test_allowed_constructs_stay_silent(tmp_path: pathlib.Path) -> None:
    """Staged outside the repository, whose config switches the fixtures off."""
    staged = tmp_path / 'clean.md'
    staged.write_text((FIXTURES / 'clean.md').read_text(encoding='utf-8'), encoding='utf-8')
    assert run_vale(str(staged)).strip() == ''


def test_a_date_warns_rather_than_fails(tmp_path: pathlib.Path) -> None:
    staged = tmp_path / 'dated.py'
    staged.write_text('def f():\n    # the MCP 2025-11-25 spec forbids it.\n    pass\n', encoding='utf-8')
    result = subprocess.run(
        ['vale', '--output=line', f'--config={CONFIG}', str(staged)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert 'subedit.DateRef' in result.stdout
    assert result.returncode == 0, 'a warning alone must not fail the run'


def test_subedit_lints_itself_clean() -> None:
    assert run_vale('src', 'tests', 'README.md').strip() == ''


def test_an_external_reference_warns_rather_than_fails(tmp_path: pathlib.Path) -> None:
    staged = tmp_path / 'ref.py'
    staged.write_text('def f():\n    # SEP-990 defines the grant this follows.\n    pass\n', encoding='utf-8')
    result = subprocess.run(
        ['vale', '--output=line', f'--config={CONFIG}', str(staged)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert 'subedit.ExternalRef' in result.stdout
    assert result.returncode == 0, 'whether a reference is public is a judgment, so it must not fail the run'


@pytest.mark.parametrize(('reference', 'flagged'), [('JIRA-123', True), ('FNV-1a', False)])
def test_a_ticket_reference_ends_at_its_digits(tmp_path: pathlib.Path, reference: str, flagged: bool) -> None:
    staged = tmp_path / 'ref.py'
    staged.write_text(f'def f():\n    # Hash it with {reference} first.\n    pass\n', encoding='utf-8')
    result = subprocess.run(
        ['vale', '--output=line', f'--config={CONFIG}', str(staged)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ('subedit.ExternalRef' in result.stdout) is flagged


@pytest.mark.parametrize('name', ['notes.md', 'notes.py'])
def test_a_full_width_semicolon_is_flagged(tmp_path: pathlib.Path, name: str) -> None:
    staged = tmp_path / name
    body = '中文分號；然後繼續。\n'  # noqa: RUF001
    staged.write_text(body if name.endswith('.md') else f'# {body}', encoding='utf-8')
    assert 'subedit.Semicolon' in run_vale(str(staged))


def test_a_markdown_note_may_tell_a_history_cite_an_issue_and_date_a_release(tmp_path: pathlib.Path) -> None:
    staged = tmp_path / 'notes.md'
    staged.write_text('Release 2026-10-24 fixes PROJ-123, which previously returned null.\n', encoding='utf-8')
    assert run_vale(str(staged)).strip() == ''


def test_edit_history_warns_in_a_comment(tmp_path: pathlib.Path) -> None:
    staged = tmp_path / 'history.py'
    staged.write_text('def f():\n    # The cache is no longer shared.\n    pass\n', encoding='utf-8')
    assert 'subedit.EditHistory' in run_vale(str(staged))
