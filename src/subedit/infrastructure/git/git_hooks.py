import dataclasses
import pathlib
import typing

from .git_repository import GitRepository


PRE_COMMIT_CONFIG = '.pre-commit-config.yaml'
PRE_COMMIT_REPOSITORY = 'https://github.com/mroops0111/subedit'

# The installed hook runs a subedit the project already has, else one uv fetches,
# which is how the plugin runs it, so it needs nothing but uv.
_SCRIPT = """#!/bin/sh
# Installed by subedit install-git-hooks. {purpose}
if command -v subedit >/dev/null 2>&1; then
    subedit=subedit
else
    subedit="uvx --python >=3.11 --from subedit>={version} subedit"
fi
{command}
"""
_EXECUTABLE = 0o755


@dataclasses.dataclass(frozen=True, slots=True)
class GitHookStage:
    """One point in a commit where git runs a hook, what subedit runs there, and the pre-commit id that runs it.

    The command is shell text, with {subedit} where the subedit command goes and {pathspecs} for the files it reads.
    """

    name: str
    command: str
    hook_id: str
    purpose: str


# The staged files are read before the commit, as changed since HEAD, and the message once git has written it.
# A fix written over a staged file leaves the commit holding the old text, so the commit waits for it to be staged.
GIT_HOOK_STAGES = (
    GitHookStage(
        'pre-commit',
        'unstaged_before=$(git diff | git hash-object --stdin)\n'
        'git diff --cached --name-only -z --diff-filter=ACMR -- {pathspecs} '
        '| xargs -0 -r {subedit} fix --write --since HEAD\n'
        'status=$?\n'
        'if [ "$(git diff | git hash-object --stdin)" != "$unstaged_before" ]; then\n'
        "    echo 'subedit laid out the staged files, so stage them and commit again.' >&2\n"
        '    exit 1\n'
        'fi\n'
        'exit $status',
        'subedit',
        'It lays out the prose the staged files changed since the last commit and stops on what needs rewriting.',
    ),
    GitHookStage(
        'commit-msg',
        '{subedit} fix --write "$1"',
        'subedit-commit-msg',
        'It lays out the commit message and stops on what needs rewriting.',
    ),
)


class GitHookInstallError(Exception):
    """A git hook subedit will not write, with what the person can do instead."""


class GitHooks:
    """The git hooks that run subedit at each stage of a commit, written as scripts or listed in pre-commit's config."""

    def __init__(
        self,
        repository: GitRepository,
        version: str,
        extensions: typing.Iterable[str],
        stages: tuple[GitHookStage, ...] = GIT_HOOK_STAGES,
    ) -> None:
        self._repository = repository
        self._version = version
        self._pathspecs = ' '.join(f"'*{extension}'" for extension in sorted(extensions))
        self._stages = stages

    def path(self, stage: GitHookStage) -> pathlib.Path:
        return self._repository.git_path(f'hooks/{stage.name}')

    def is_installed(self) -> bool:
        return all(self._runs_subedit(stage) for stage in self._stages)

    def install(self) -> str:
        """Write each missing hook and say what was done, or raise when another tool holds one or should write it."""
        if (self._repository.root / PRE_COMMIT_CONFIG).is_file() and not self.is_installed():
            raise GitHookInstallError(self._pre_commit_steps())
        done: list[str] = []
        refusals: list[str] = []
        for stage in self._stages:
            path = self.path(stage)
            if self._runs_subedit(stage):
                done.append(f'A {stage.name} hook already runs subedit, at {path}.')
            elif self._installed_text(stage) is not None:
                refusals.append(
                    f'{path} already holds a {stage.name} hook that is not subedit, so it was left alone. '
                    f'Add these lines to it to run both:\n\n{self._command(stage, "subedit")}\n'
                )
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(self._script(stage), encoding='utf-8')
                path.chmod(_EXECUTABLE)
                done.append(f'Installed a {stage.name} hook at {path}.')
        if refusals:
            raise GitHookInstallError('\n'.join(done + refusals))
        return '\n'.join(done)

    def _script(self, stage: GitHookStage) -> str:
        return _SCRIPT.format(purpose=stage.purpose, command=self._command(stage, '$subedit'), version=self._version)

    def _command(self, stage: GitHookStage, subedit: str) -> str:
        return stage.command.format(subedit=subedit, pathspecs=self._pathspecs)

    def _runs_subedit(self, stage: GitHookStage) -> bool:
        installed = self._installed_text(stage)
        if installed is None:
            return False
        return 'subedit' in installed or ('pre-commit' in installed and self._pre_commit_lists(stage))

    def _installed_text(self, stage: GitHookStage) -> str | None:
        try:
            return self.path(stage).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return None

    def _pre_commit_text(self) -> str:
        try:
            return (self._repository.root / PRE_COMMIT_CONFIG).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return ''

    def _pre_commit_lists(self, stage: GitHookStage) -> bool:
        return f'id: {stage.hook_id}\n' in self._pre_commit_text() + '\n'

    # A project on pre-commit keeps its hooks in its own config, which subedit leaves to the person to edit.
    def _pre_commit_steps(self) -> str:
        install = ' '.join(f'--hook-type {stage.name}' for stage in self._stages)
        command = f'`pre-commit install {install}`'
        missing = [stage for stage in self._stages if not self._pre_commit_lists(stage)]
        if not missing:
            return (
                f'{PRE_COMMIT_CONFIG} lists the subedit hooks, but pre-commit has not installed them, so run {command}.'
            )
        entry = f'  - repo: {PRE_COMMIT_REPOSITORY}\n    rev: v{self._version}\n    hooks:\n' + ''.join(
            f'      - id: {stage.hook_id}\n' for stage in missing
        )
        return (
            f'This project runs its hooks through pre-commit, so add this under repos in {PRE_COMMIT_CONFIG}:\n\n'
            f'{entry}\nThen run {command}.'
        )
