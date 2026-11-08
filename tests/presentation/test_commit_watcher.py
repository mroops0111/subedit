import pathlib

import pytest
from factories import Project

from subedit.presentation.commit_watcher import CommitWatcher
from subedit.presentation.harnesses import ShellCommand


def writes_of(directory: pathlib.Path, command: str) -> list[str | None]:
    return [written.read() for written in CommitWatcher().writes(ShellCommand(command, directory))]


@pytest.mark.parametrize(
    'command',
    [
        'git commit -m "Add the parser"',
        'git add . && git commit -F message.txt',
        'git -c core.editor=true commit --amend',
    ],
)
def test_a_commit_command_hands_back_the_message_just_committed(repository: Project, command: str) -> None:
    repository.git('commit', '-q', '--allow-empty', '-m', 'Add the parser')

    assert writes_of(repository.root, command) == ['Add the parser\n\n']


def test_git_dash_c_moves_where_the_commit_ran(repository: Project, tmp_path_factory: pytest.TempPathFactory) -> None:
    repository.git('commit', '-q', '--allow-empty', '-m', 'Add the parser')
    elsewhere = tmp_path_factory.mktemp('elsewhere')

    assert writes_of(elsewhere, f'git -C {repository.root} commit -m x') == ['Add the parser\n\n']


@pytest.mark.parametrize('command', ['git log --grep commit', 'echo commit', 'git commit-tree HEAD^{tree}'])
def test_other_commands_write_nothing(repository: Project, command: str) -> None:
    repository.git('commit', '-q', '--allow-empty', '-m', 'Add the parser')

    assert writes_of(repository.root, command) == []


def test_a_commit_command_that_made_no_commit_writes_nothing(repository: Project) -> None:
    repository.git('checkout', '-q', '-b', 'topic')

    assert writes_of(repository.root, 'git commit -m x') == []


def test_the_message_is_read_as_the_file_git_writes_it_to(repository: Project) -> None:
    repository.git('commit', '-q', '--allow-empty', '-m', 'Add the parser')
    (written,) = CommitWatcher().writes(ShellCommand('git commit', repository.root))

    assert written.path.name == 'COMMIT_EDITMSG'
    assert 'git commit --amend --only -F -' in (written.write_back('Add the parser\n') or '')
