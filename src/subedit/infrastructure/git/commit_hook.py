import pathlib

from .git_repository import GitRepository


HOOK_ID = 'subedit-commit-msg'
PRE_COMMIT_CONFIG = '.pre-commit-config.yaml'

# The installed hook runs a subedit the project already has, else one uv fetches,
# which is how the plugin runs it, so it needs nothing but uv.
_SCRIPT = """#!/bin/sh
# Installed by subedit install-hook. It lays out the commit message and stops on what needs rewriting.
if command -v subedit >/dev/null 2>&1; then
    exec subedit fix --write "$1"
fi
exec uvx --python '>=3.11' --from 'subedit>={version}' subedit fix --write "$1"
"""
_EXECUTABLE = 0o755


class HookInstallError(Exception):
    """A commit-msg hook subedit will not write, with what the person can do instead."""


class CommitHook:
    """The git commit-msg hook that runs subedit, written as a script or listed in pre-commit's config."""

    def __init__(self, repository: GitRepository, version: str) -> None:
        self._repository = repository
        self._version = version

    @property
    def path(self) -> pathlib.Path:
        return self._repository.git_path('hooks/commit-msg')

    def is_installed(self) -> bool:
        installed = self._installed_text()
        if installed is None:
            return False
        return 'subedit' in installed or ('pre-commit' in installed and self._pre_commit_lists_it())

    def install(self) -> str:
        """Write the hook and say what was done, or raise when another tool holds the hook or should write it."""
        if self.is_installed():
            return f'A commit-msg hook already runs subedit, at {self.path}.'
        if (self._repository.root / PRE_COMMIT_CONFIG).is_file():
            raise HookInstallError(self._pre_commit_steps())
        if self._installed_text() is not None:
            raise HookInstallError(
                f'{self.path} already holds a commit-msg hook that is not subedit, so it was left alone. '
                'Add `subedit fix --write "$1"` to it to run both.'
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(_SCRIPT.format(version=self._version), encoding='utf-8')
        self.path.chmod(_EXECUTABLE)
        return f'Installed a commit-msg hook at {self.path}.'

    def _installed_text(self) -> str | None:
        try:
            return self.path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return None

    def _pre_commit_lists_it(self) -> bool:
        try:
            return HOOK_ID in (self._repository.root / PRE_COMMIT_CONFIG).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return False

    # A project on pre-commit keeps its hooks in its own config, which subedit leaves to the person to edit.
    def _pre_commit_steps(self) -> str:
        command = '`pre-commit install --hook-type commit-msg`'
        if self._pre_commit_lists_it():
            return f'{PRE_COMMIT_CONFIG} lists {HOOK_ID}, but pre-commit has not installed it, so run {command}.'
        entry = (
            '  - repo: https://github.com/mroops0111/subedit\n'
            f'    rev: v{self._version}\n'
            '    hooks:\n'
            f'      - id: {HOOK_ID}\n'
        )
        return (
            f'This project runs its hooks through pre-commit, so add this under repos in {PRE_COMMIT_CONFIG}:\n\n'
            f'{entry}\nThen run {command}.'
        )
