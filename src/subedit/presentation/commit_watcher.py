import pathlib
import re

from ..infrastructure import GitRepository
from .agent_writes import AgentWrite, ShellWatcher
from .harnesses import ShellCommand


# git takes its own options before the subcommand, and -C among them moves where it runs.
_GIT_COMMIT = re.compile(r'(?:^|[\s;&|(])git((?:\s+(?:-C\s+\S+|-c\s+\S+|--?[\w-]+(?:=\S+)?))*)\s+commit(?=\s|$|[;&|)])')
_CHANGE_DIRECTORY = re.compile(r'-C\s+(\S+)')
# git writes the message it commits to this file, so a commit is checked as that file would be.
_MESSAGE_FILE = 'COMMIT_EDITMSG'


class CommittedMessage(AgentWrite):
    """The message of a commit an agent just made, which only an amend can change."""

    def __init__(self, repository: GitRepository, message: str) -> None:
        self._repository = repository
        self._message = message

    @property
    def path(self) -> pathlib.Path:
        return self._repository.git_path(_MESSAGE_FILE)

    def read(self) -> str | None:
        return self._message

    def write_back(self, text: str) -> str | None:
        """Hand the text back, since amending rewrites history, which is the agent's call."""
        return (
            'subedit: the commit just made needs its message laid out. If it is not pushed yet, '
            'amend it with `git commit --amend --only -F -`, which keeps whatever is staged out of the commit, '
            f'and this text:\n\n{text.rstrip()}'
        )


class CommitWatcher(ShellWatcher):
    """Recognises git commit, and reads back the message of a commit it made, as HEAD's reflog shows."""

    @property
    def keyword(self) -> str:
        return 'commit'

    def writes(self, command: ShellCommand) -> tuple[AgentWrite, ...]:
        commit = _GIT_COMMIT.search(command.command)
        if commit is None:
            return ()
        directory = command.directory
        for moved in _CHANGE_DIRECTORY.finditer(commit.group(1)):
            directory = directory / moved.group(1).strip('\'"')
        repository = GitRepository.at(directory)
        message = repository.just_committed_message() if repository else None
        if repository is None or message is None:
            return ()
        return (CommittedMessage(repository, message),)
