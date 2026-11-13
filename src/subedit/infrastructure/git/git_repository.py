import dataclasses
import pathlib
import shutil
import subprocess
import time


# A commit an agent just made is the newest entry in HEAD's reflog,
# and a command that ran long, such as one whose own hooks ran a test suite, still finished within this many seconds.
_RECENT_SECONDS = 600
# The reflog names each move of HEAD by the command that made it, as in "commit (amend): ...".
_COMMIT_ACTION = 'commit'


@dataclasses.dataclass(frozen=True, slots=True)
class GitRepository:
    """A git working tree, read through the git command so that git's own settings, such as core.hooksPath, apply."""

    root: pathlib.Path

    @classmethod
    def at(cls, directory: pathlib.Path) -> 'GitRepository | None':
        """The working tree holding the directory, or None outside one or where git is not installed."""
        root = _git(directory, 'rev-parse', '--show-toplevel')
        return cls(pathlib.Path(root)) if root else None

    def git_path(self, name: str) -> pathlib.Path:
        """Where git keeps a file it owns, such as hooks/commit-msg or COMMIT_EDITMSG."""
        relative = _git(self.root, 'rev-parse', '--git-path', name) or f'.git/{name}'
        return (self.root / relative).resolve()

    def commit_named(self, revision: str) -> str | None:
        """The commit a revision names, or None when it names none.

        A range such as origin/master...HEAD names where its two sides meet, as git diff reads it.
        """
        if '...' in revision:
            left, _, right = revision.partition('...')
            return _git(self.root, 'merge-base', left or 'HEAD', right or 'HEAD')
        return _git(self.root, 'rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}')

    def text_at(self, commit: str, path: pathlib.Path) -> str | None:
        """The text a file had at a commit, or None when the commit held no such file, or it lies outside the tree."""
        try:
            relative = path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return None
        return _git(self.root, 'show', f'{commit}:{relative}', strip=False)

    def commit_messages(self, count: int) -> tuple[str, ...]:
        """The messages of the newest commits from HEAD, leaving out merges, whose messages git writes."""
        log = _git(self.root, 'log', f'--max-count={count}', '--no-merges', '--format=%B%x00', strip=False)
        return tuple(f'{message.strip()}\n' for message in (log or '').split('\0') if message.strip())

    def recent_commit_message(self) -> str | None:
        """The message of a commit made in the last few minutes, or None when HEAD last moved for another reason."""
        entry = _git(self.root, 'reflog', '-1', '--date=unix', '--format=%gd %gs')
        if not entry:
            return None
        selector, _, action = entry.partition(' ')
        moved_at = selector.removeprefix('HEAD@{').removesuffix('}')
        if not action.startswith(_COMMIT_ACTION) or not moved_at.isdigit():
            return None
        if time.time() - int(moved_at) > _RECENT_SECONDS:
            return None
        return _git(self.root, 'log', '-1', '--format=%B', strip=False)


# Output is None when git is missing or the command fails, since every caller treats both as no answer.
def _git(directory: pathlib.Path, *arguments: str, strip: bool = True) -> str | None:
    executable = shutil.which('git')
    if executable is None:
        return None
    try:
        # The arguments are subedit's own, never text from the payload.
        completed = subprocess.run(  # noqa: S603
            [executable, *arguments], cwd=directory, capture_output=True, text=True, encoding='utf-8', check=False
        )
    except (OSError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() if strip else completed.stdout
