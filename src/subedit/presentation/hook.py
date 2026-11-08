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
    CommitHook,
    ConfigError,
    GitRepository,
    language_id_for,
)
from . import report as reporters
from .harnesses import ALL_HARNESSES, BLOCK_EXIT, AgentHarness, Payload, resolve


_HELP_FLAGS = frozenset({'--help', '-h', '--harnesses'})
# git writes the message it commits to this file, so a commit is checked as that file would be.
_COMMIT_MESSAGE_FILE = 'COMMIT_EDITMSG'
_HOOK_OFFER = (
    'This repository configures subedit, but no git commit-msg hook runs it, '
    'so a commit made outside this session goes unchecked. Offer the user, once, to run `subedit install-hook`, '
    'and run it only if they agree.'
)
_AMEND = (
    'subedit: the commit just made needs its message changed. If it is not pushed yet, '
    'amend it with `git commit --amend --only -F -`, which keeps whatever is staged out of the commit.'
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
    """Answer one agent payload, whether it opens a session, makes a commit, or edits files.

    An edit is fixed in place, and the agent is blocked only on a finding that needs an author.
    A commit is never rewritten by the hook, since amending history is the agent's call.
    """
    for harness in ALL_HARNESSES:
        directory = harness.session_directory(payload)
        if directory is not None:
            return _offer_commit_hook(harness, directory)
        directory = harness.commit_directory(payload)
        if directory is not None:
            return _check_commit(harness, directory)
    return _fix_edits(payload, write=write)


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


def _fix_edits(payload: Payload, *, write: bool) -> HookResult:
    recognition = resolve(payload)
    if recognition is None:
        return HookResult(exit_code=0)
    harness, edited_paths = recognition
    if not edited_paths:
        return HookResult(exit_code=0, harness_name=harness.metadata.name)

    fixer = _fixer()
    author_messages: list[str] = []
    advice_messages: list[str] = []
    repaired_paths: list[str] = []

    for source_path in edited_paths:
        try:
            source_text = source_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        language_id = language_id_for(source_path)
        try:
            # A plugin installed once reaches every project, so only one that configures subedit opts in.
            if language_id is None or not DEFAULT_CONFIG_SOURCE.is_adopted(str(source_path)):
                continue
            rule_set = DEFAULT_CONFIG_SOURCE.resolve(str(source_path))
        except ConfigError as error:
            # The project asked for subedit, so a config it cannot read goes back to the agent to fix.
            author_messages.append(f'subedit: {error}')
            continue
        document = Document(uri=source_path.resolve().as_uri(), text=source_text, language_id=language_id)
        fix_result = fixer.run(document, rule_set)
        if fix_result.has_changes and write:
            source_path.write_text(fix_result.document.text, encoding='utf-8')
            repaired_paths.append(str(source_path))
        brief_report = reporters.brief(fix_result.document, fix_result.report)
        if brief_report:
            author_messages.append(brief_report)
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
    # A blocked edit is already going back to the model, so its warnings ride along.
    return HookResult(
        exit_code=BLOCK_EXIT,
        stderr='\n\n'.join(author_messages + advice_messages),
        repaired_paths=tuple(repaired_paths),
        harness_name=harness.metadata.name,
    )


# A session that opens in a repository reading commit messages hears once that its git hook is missing.
def _offer_commit_hook(harness: AgentHarness, directory: pathlib.Path) -> HookResult:
    quiet = HookResult(exit_code=0, harness_name=harness.metadata.name)
    repository = GitRepository.at(directory)
    if repository is None:
        return quiet
    message_path = repository.git_path(_COMMIT_MESSAGE_FILE)
    try:
        if not DEFAULT_CONFIG_SOURCE.is_adopted(str(message_path)):
            return quiet
        rule_set = DEFAULT_CONFIG_SOURCE.resolve(str(message_path))
    except ConfigError:
        # The first edit reports a config subedit cannot read, and nothing has been asked of the agent yet.
        return quiet
    if rule_set.for_language(language_id_for(message_path) or '').is_off:
        return quiet
    if CommitHook(repository, __version__).is_installed():
        return quiet
    return HookResult(exit_code=0, stdout=harness.session_output(_HOOK_OFFER), harness_name=harness.metadata.name)


def _check_commit(harness: AgentHarness, directory: pathlib.Path) -> HookResult:
    quiet = HookResult(exit_code=0, harness_name=harness.metadata.name)
    repository = GitRepository.at(directory)
    message = repository.just_committed_message() if repository else None
    if repository is None or message is None:
        return quiet
    message_path = repository.git_path(_COMMIT_MESSAGE_FILE)
    try:
        # A commit is checked where an edit would be, in a project that configures subedit.
        if not DEFAULT_CONFIG_SOURCE.is_adopted(str(message_path)):
            return quiet
        rule_set = DEFAULT_CONFIG_SOURCE.resolve(str(message_path))
    except ConfigError as error:
        return HookResult(exit_code=BLOCK_EXIT, stderr=f'subedit: {error}', harness_name=harness.metadata.name)
    document = Document(uri=message_path.as_uri(), text=message, language_id=language_id_for(message_path) or '')
    fix_result = _fixer().run(document, rule_set)
    findings = reporters.brief(fix_result.document, fix_result.report)
    advice = reporters.advice(fix_result.document, fix_result.report)
    if not findings and not fix_result.has_changes:
        return HookResult(
            exit_code=0,
            stdout=harness.advisory_output(advice) if advice else '',
            harness_name=harness.metadata.name,
        )
    messages = [_AMEND]
    if findings:
        messages.append(findings)
    if fix_result.has_changes:
        layout = 'Laid out, the message reads as below'
        if findings:
            layout += ', before the rewrites named above'
        messages.append(f'{layout}:\n\n{fix_result.document.text.rstrip()}')
    if advice:
        messages.append(advice)
    return HookResult(exit_code=BLOCK_EXIT, stderr='\n\n'.join(messages), harness_name=harness.metadata.name)


def _fixer() -> Fixer:
    return Fixer(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)), EXTERNAL_LINTERS)


if __name__ == '__main__':
    sys.exit(main())
