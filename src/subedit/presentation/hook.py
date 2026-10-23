import dataclasses
import json
import pathlib
import sys

from ..application import Fixer, Linter, RuleEngine
from ..domain.models.document import Document
from ..infrastructure import ALL_RULES, DEFAULT_CONFIG_SOURCE, DEFAULT_PARSER, EXTERNAL_LINTERS, language_id_for
from . import report as reporters
from .harnesses import ALL_HARNESSES, BLOCK_EXIT, Payload, resolve


HELP_FLAGS = frozenset({'--help', '-h', '--harnesses'})


@dataclasses.dataclass(frozen=True, slots=True)
class HookResult:
    exit_code: int
    stderr: str = ''
    stdout: str = ''
    repaired_paths: tuple[str, ...] = ()
    harness_name: str = ''

    @property
    def is_blocking(self) -> bool:
        return self.exit_code == BLOCK_EXIT


def run(payload: Payload, *, write: bool = True) -> HookResult:
    recognition = resolve(payload)
    if recognition is None:
        return HookResult(exit_code=0)
    harness, edited_paths = recognition
    if not edited_paths:
        return HookResult(exit_code=0, harness_name=harness.metadata.name)

    fixer = Fixer(Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES)), EXTERNAL_LINTERS)
    author_messages: list[str] = []
    advice_messages: list[str] = []
    repaired_paths: list[str] = []

    for source_path in edited_paths:
        try:
            source_text = source_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        language_id = language_id_for(source_path)
        # A plugin installed once reaches every project, so only one that configures subedit opts in.
        if language_id is None or not DEFAULT_CONFIG_SOURCE.is_adopted(str(source_path)):
            continue
        document = Document(uri=source_path.resolve().as_uri(), text=source_text, language_id=language_id)
        fix_result = fixer.run(document, DEFAULT_CONFIG_SOURCE.resolve(str(source_path)))
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


def edited_files(payload: Payload) -> tuple[pathlib.Path, ...]:
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
    if HELP_FLAGS & set(sys.argv[1:]):
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


if __name__ == '__main__':
    sys.exit(main())
