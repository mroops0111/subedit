import dataclasses
import json
import pathlib
import sys

from .. import __version__
from ..application import Fixer, Linter, RuleEngine
from ..domain.models.document import Document
from ..infrastructure import (
    ALL_RULES,
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_PARSER,
    EXTERNAL_LINTERS,
    ConfigError,
    GitHooks,
    GitRepository,
    language_id_for,
)
from . import report as reporters
from .agent_writes import AgentWrite, EditedFile, ShellWatcher
from .commit_watcher import CommitWatcher
from .harnesses import ALL_HARNESSES, BLOCK_EXIT, AgentHarness, Payload, resolve


# Each recognises a shell command that writes text some surface reads, so a new one is one more watcher.
SHELL_WATCHERS: tuple[ShellWatcher, ...] = (CommitWatcher(),)

_HELP_FLAGS = frozenset({'--help', '-h', '--harnesses'})
_HOOK_OFFER = (
    'This repository configures subedit, but its git hooks do not run it, '
    'so text written outside this session goes unchecked until an agent edits it. '
    'Offer the user, once, to run `subedit install-hook`, and run it only if they agree.'
)


@dataclasses.dataclass(frozen=True, slots=True)
class HookResult:
    """What the hook tells the agent, through its exit code and output, and which files it repaired."""

    exit_code: int
    stderr: str = ''
    stdout: str = ''
    repaired_paths: tuple[str, ...] = ()
    harness_name: str = ''

    @property
    def is_blocking(self) -> bool:
        return self.exit_code == BLOCK_EXIT


def run(payload: Payload, *, write: bool = True) -> HookResult:
    """Answer one agent payload, whether it opens a session, runs a shell command, or edits files.

    What the agent wrote is fixed in place where the hook can write it, and handed back where it cannot.
    The agent is blocked only on a finding that needs an author, or on a fix only it can apply.
    """
    for harness in ALL_HARNESSES:
        directory = harness.session_directory(payload)
        if directory is not None:
            return _offer_git_hooks(harness, directory)
        command = harness.shell_command(payload)
        if command is not None:
            return _check(
                harness, tuple(written for watcher in SHELL_WATCHERS for written in watcher.writes(command)), write
            )
    recognition = resolve(payload)
    if recognition is None:
        return HookResult(exit_code=0)
    harness, edited_paths = recognition
    return _check(harness, tuple(EditedFile(path) for path in edited_paths), write)


def edited_files(payload: Payload) -> tuple[pathlib.Path, ...]:
    """The files a payload edited, whichever agent sent it."""
    recognition = resolve(payload)
    if recognition is None:
        return ()
    _, edited_paths = recognition
    return edited_paths


def describe_harnesses() -> str:
    """Say which payload shapes reach this hook, so a caller can check its own.

    Unrecognised payloads exit quietly, since an agent sends many that are none of our business.
    That silence is why the shapes have to be askable for.
    """
    help_lines = ['subedit-hook reads one agent payload on stdin.', '']
    for harness in ALL_HARNESSES:
        metadata = harness.metadata
        help_lines.extend([metadata.name, f'  {metadata.summary}', f'  {json.dumps(metadata.example)}', ''])
    help_lines.extend(
        [
            'A payload no harness recognises exits 0 and changes nothing.',
            'Outside an agent, use subedit fix --write and subedit check instead.',
        ]
    )
    return '\n'.join(help_lines)


def main() -> int:
    if _HELP_FLAGS & set(sys.argv[1:]):
        sys.stdout.write(describe_harnesses() + '\n')
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    hook_result = run(payload)
    if hook_result.stdout:
        sys.stdout.write(hook_result.stdout + '\n')
    if hook_result.stderr:
        sys.stderr.write(hook_result.stderr + '\n')
    return hook_result.exit_code


def _check(harness: AgentHarness, writes: tuple[AgentWrite, ...], write: bool) -> HookResult:
    fixer = Fixer(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)), EXTERNAL_LINTERS)
    author_messages: list[str] = []
    advice_messages: list[str] = []
    repaired_paths: list[str] = []

    for agent_write in writes:
        source_path = agent_write.path
        source_text = agent_write.read()
        language_id = language_id_for(source_path)
        if source_text is None or language_id is None:
            continue
        try:
            # A plugin installed once reaches every project, so only one that configures subedit opts in.
            if not DEFAULT_CONFIG_SOURCE.is_adopted(str(source_path)):
                continue
            rule_set = DEFAULT_CONFIG_SOURCE.resolve(str(source_path))
        except ConfigError as error:
            # The project asked for subedit, so a config it cannot read goes back to the agent to fix.
            author_messages.append(f'subedit: {error}')
            continue
        document = Document(uri=source_path.resolve().as_uri(), text=source_text, language_id=language_id)
        fix_result = fixer.run(document, rule_set)
        brief_report = reporters.brief(fix_result.document, fix_result.report)
        if brief_report:
            author_messages.append(brief_report)
        if fix_result.has_changes and write:
            unwritten = agent_write.write_back(fix_result.document.text)
            if unwritten is None:
                repaired_paths.append(str(source_path))
            else:
                author_messages.append(unwritten)
        advice_report = reporters.advice(fix_result.document, fix_result.report)
        if advice_report:
            advice_messages.append(advice_report)

    if not author_messages:
        return HookResult(
            exit_code=0,
            stdout=harness.advisory_output('\n\n'.join(advice_messages)) if advice_messages else '',
            repaired_paths=tuple(repaired_paths),
            harness_name=harness.metadata.name,
        )
    # A blocked write is already going back to the model, so its warnings ride along.
    return HookResult(
        exit_code=BLOCK_EXIT,
        stderr='\n\n'.join(author_messages + advice_messages),
        repaired_paths=tuple(repaired_paths),
        harness_name=harness.metadata.name,
    )


# A session that opens in a repository configuring subedit hears once that its git hooks do not run it.
def _offer_git_hooks(harness: AgentHarness, directory: pathlib.Path) -> HookResult:
    quiet = HookResult(exit_code=0, harness_name=harness.metadata.name)
    repository = GitRepository.at(directory)
    try:
        if repository is None or not DEFAULT_CONFIG_SOURCE.is_adopted(str(repository.root)):
            return quiet
    except ConfigError:
        # The first edit reports a config subedit cannot read, and nothing has been asked of the agent yet.
        return quiet
    if GitHooks(repository, __version__).is_installed():
        return quiet
    return HookResult(exit_code=0, stdout=harness.session_output(_HOOK_OFFER), harness_name=harness.metadata.name)


if __name__ == '__main__':
    sys.exit(main())
