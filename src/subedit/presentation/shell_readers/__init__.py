from .commit_reader import CommitReader, CommittedMessage
from .shell_command_reader import ShellCommandReader


# Each recognises a shell command that writes text some surface reads, so a new one is one more reader.
ALL_SHELL_READERS: tuple[ShellCommandReader, ...] = (CommitReader(),)


__all__ = ['ALL_SHELL_READERS', 'CommitReader', 'CommittedMessage', 'ShellCommandReader']
