import pathlib
import subprocess

import pytest
from factories import Project

from subedit.infrastructure import EXTENSIONS, GitHookInstallError, GitHooks, GitRepository
from subedit.infrastructure.git import GIT_HOOK_STAGES, GitHookStage


VERSION = '9.9.9'
PRE_COMMIT_ENTRY = 'repos:\n  - repo: https://github.com/mroops0111/subedit\n    hooks:\n      - id: subedit\n      - id: subedit-commit-msg\n'


def opened(directory: pathlib.Path) -> GitRepository:
    opened_repository = GitRepository.at(directory)
    assert opened_repository is not None, f'{directory} is not inside a working tree'
    return opened_repository


def hooks_for(repository: Project) -> GitHooks:
    return GitHooks(opened(repository.root), VERSION, EXTENSIONS)


def stage(name: str) -> GitHookStage:
    return next(stage for stage in GIT_HOOK_STAGES if stage.name == name)


def test_a_directory_outside_any_repository_opens_none(tmp_path: pathlib.Path) -> None:
    assert GitRepository.at(tmp_path) is None


def test_a_subdirectory_opens_its_working_tree(repository: Project) -> None:
    (repository.root / 'packages').mkdir()

    assert opened(repository.root / 'packages').root == repository.root.resolve()


def test_a_commit_just_made_gives_its_message(repository: Project) -> None:
    repository.git('commit', '-q', '--allow-empty', '-m', 'Add the parser\n\nIt reads the subject.')

    assert opened(repository.root).recent_commit_message() == 'Add the parser\n\nIt reads the subject.\n\n'


def test_head_moved_by_anything_but_a_commit_gives_no_message(repository: Project) -> None:
    repository.git('checkout', '-q', '-b', 'topic')

    assert opened(repository.root).recent_commit_message() is None


def test_a_revision_names_its_commit_and_a_range_names_where_its_sides_meet(repository: Project) -> None:
    opened_repository = opened(repository.root)
    head = repository.git('rev-parse', 'HEAD').strip()

    assert opened_repository.commit_named('HEAD') == head
    assert opened_repository.commit_named('HEAD...') == head, 'git diff reads A... as from where A and HEAD meet'
    assert opened_repository.commit_named('no-such-branch') is None


def test_text_at_reads_a_file_as_a_commit_held_it(repository: Project) -> None:
    notes = repository.write('notes.md', 'Old text.\n')
    repository.git('add', 'notes.md')
    repository.git('commit', '-q', '-m', 'Add notes')
    notes.write_text('New text.\n', encoding='utf-8')
    opened_repository = opened(repository.root)

    assert opened_repository.text_at('HEAD', notes) == 'Old text.\n'
    assert opened_repository.text_at('HEAD', repository.root / 'missing.md') is None
    assert opened_repository.text_at('HEAD', pathlib.Path('/elsewhere/notes.md')) is None


def test_the_hook_path_follows_core_hooks_path(repository: Project) -> None:
    repository.git('config', 'core.hooksPath', '.githooks')

    assert hooks_for(repository).path(stage('commit-msg')) == repository.root.resolve() / '.githooks' / 'commit-msg'


@pytest.mark.parametrize(
    ('name', 'command'), [('pre-commit', 'fix --write --since HEAD'), ('commit-msg', 'fix --write "$1"')]
)
def test_install_writes_an_executable_hook_at_each_stage(repository: Project, name: str, command: str) -> None:
    hooks = hooks_for(repository)

    assert f'Installed a {name} hook' in hooks.install()
    script = hooks.path(stage(name)).read_text(encoding='utf-8')
    assert script.startswith('#!/bin/sh\n')
    assert f'$subedit {command}' in script
    assert f'subedit>={VERSION} subedit' in script, 'the fallback must run at least the subedit that installed it'
    assert hooks.path(stage(name)).stat().st_mode & 0o111
    assert hooks.is_installed()


def test_a_second_install_changes_nothing(repository: Project) -> None:
    hooks = hooks_for(repository)
    hooks.install()

    assert hooks.install().count('already') == len(GIT_HOOK_STAGES)


def test_a_hook_another_tool_holds_is_left_alone_and_the_rest_installed(repository: Project) -> None:
    hooks = hooks_for(repository)
    repository.write('.git/hooks/commit-msg', '#!/bin/sh\nnpx commitlint --edit "$1"\n')

    with pytest.raises(GitHookInstallError, match='not subedit') as raised:
        hooks.install()
    assert 'Installed a pre-commit hook' in str(raised.value)
    assert 'commitlint' in hooks.path(stage('commit-msg')).read_text(encoding='utf-8')
    assert not hooks.is_installed()


def test_a_pre_commit_project_is_told_the_entries_to_add(repository: Project) -> None:
    repository.write('.pre-commit-config.yaml', 'repos: []\n')

    with pytest.raises(GitHookInstallError) as raised:
        hooks_for(repository).install()
    message = str(raised.value)
    assert 'id: subedit\n' in message
    assert 'id: subedit-commit-msg\n' in message
    assert f'rev: v{VERSION}' in message
    assert 'pre-commit install --hook-type pre-commit --hook-type commit-msg' in message


def test_a_pre_commit_project_listing_the_hooks_is_told_to_install_them(repository: Project) -> None:
    repository.write('.pre-commit-config.yaml', PRE_COMMIT_ENTRY)

    with pytest.raises(GitHookInstallError, match='has not installed them'):
        hooks_for(repository).install()


def test_pre_commit_running_the_listed_hooks_counts_as_installed(repository: Project) -> None:
    repository.write('.pre-commit-config.yaml', PRE_COMMIT_ENTRY)
    for name in ('pre-commit', 'commit-msg'):
        repository.write(f'.git/hooks/{name}', '#!/usr/bin/env bash\n# File generated by pre-commit\n')

    assert hooks_for(repository).is_installed()


OLD_PARAGRAPH = 'Cap the size so the mmap does not\nblow past it, an unbounded value faults.\n'
NEW_PARAGRAPH = 'Keep the cache warm so a restart does not\nreload it, a cold read stalls.\n'


def test_the_pre_commit_hook_lays_out_only_the_staged_change_and_waits_for_it_to_be_staged(
    repository: Project,
) -> None:
    repository.write('subedit.toml', '[subedit]\n')
    notes = repository.write('notes.md', OLD_PARAGRAPH)
    repository.write('image.png', 'not prose')
    repository.git('add', '.')
    repository.git('commit', '-q', '--no-verify', '-m', 'Add notes')
    hooks_for(repository).install()
    notes.write_text(OLD_PARAGRAPH + '\n' + NEW_PARAGRAPH, encoding='utf-8')
    repository.git('add', 'notes.md')

    with pytest.raises(subprocess.CalledProcessError) as raised:
        repository.git('commit', '-q', '-m', 'Add a paragraph')
    assert 'stage them and commit again' in raised.value.stderr
    assert notes.read_text(encoding='utf-8') == (
        OLD_PARAGRAPH + '\nKeep the cache warm so a restart does not reload it, a cold read stalls.\n'
    ), "the committed paragraph is someone else's to lay out"

    repository.git('add', 'notes.md')
    repository.git('commit', '-q', '-m', 'Add a paragraph')
