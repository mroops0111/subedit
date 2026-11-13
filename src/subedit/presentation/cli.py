import dataclasses
import difflib
import pathlib
import sys
import typing

import typer

from .. import __version__
from ..application import (
    CorpusMeter,
    Fixer,
    Linter,
    ReportAggregator,
    RuleEngine,
)
from ..domain.models.document import Document
from ..domain.models.rule_set import RuleSet
from ..domain.models.text import source_lines
from ..domain.ports.baseline_source import BaselineSource
from ..domain.ports.external_linter import ExternalLinter
from ..infrastructure import (
    ALL_RULES,
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_PARSER,
    EXTENSIONS,
    EXTERNAL_LINTERS,
    GENERATED_NAMES,
    VENDOR_DIRECTORIES,
    ConfigError,
    FileBaselineSource,
    GitHookInstallError,
    GitHooks,
    GitRepository,
    GitRevisionBaselineSource,
    language_id_for,
)
from . import report as reporters
from . import rule_reference, statistics_report


app = typer.Typer(
    add_completion=False, help='A subeditor for AI agents, keeping every sentence they write to your house style.'
)

_FORMATTERS = {
    'full': reporters.full,
    'actionable': reporters.actionable,
    'json': reporters.as_json,
}
_STATISTICS_FORMATTERS = {'text': statistics_report.text, 'json': statistics_report.as_json}
# A path of - reads one draft from stdin, as ruff, Prettier, and ESLint take it.
_STDIN = pathlib.Path('-')
_STDIN_FILENAME = typer.Option(
    None, '--stdin-filename', help='The file a draft read from stdin stands for, which picks its surface and config.'
)
# A change is read since where it began, a git revision or a file, so only the prose it touched is checked.
_SINCE = typer.Option(
    None,
    '--since',
    help='Read only the prose changed since a git revision, such as HEAD or origin/master..., '
    'or since a file, written as ./old.md.',
)

ConfigT = typing.TypeVar('ConfigT')


@app.command()
def check(
    paths: list[pathlib.Path] = typer.Argument(None, help='Files or directories to check, or - for a draft on stdin.'),
    output: str = typer.Option('full', '--output', help='full, actionable, or json.'),
    delegate: bool = typer.Option(True, '--delegate/--no-delegate', help='Also run Vale and AutoCorrect.'),
    stdin_filename: pathlib.Path | None = _STDIN_FILENAME,
    since: str | None = _SINCE,
) -> None:
    """Report findings, and exit non-zero when any is an error."""
    documents = _with_baselines(_documents_to_read(paths, stdin_filename=stdin_filename), since)
    formatter = _FORMATTERS.get(output)
    if formatter is None:
        typer.echo(f'Unknown output format {output!r}. Choose full, actionable, or json.', err=True)
        raise typer.Exit(2)

    aggregator = _build_report_aggregator(delegate)
    has_errors = False
    for document in documents:
        report = aggregator.run(document, _rules_for(document))
        has_errors = has_errors or report.has_errors
        rendered_report = formatter(document, report)
        if rendered_report:
            typer.echo(rendered_report)
    raise typer.Exit(1 if has_errors else 0)


@app.command()
def fix(
    paths: list[pathlib.Path] = typer.Argument(None, help='Files or directories to fix, or - for a draft on stdin.'),
    write: bool = typer.Option(False, '--write', help='Write changes instead of printing a diff.'),
    delegate: bool = typer.Option(True, '--delegate/--no-delegate', help='Also run Vale and AutoCorrect.'),
    stdin_filename: pathlib.Path | None = _STDIN_FILENAME,
    since: str | None = _SINCE,
) -> None:
    """Apply mechanical fixes, printing a diff unless told to write, and report what needs an author.

    A draft read from stdin comes back fixed on stdout, with the findings on stderr, so a pipe keeps only the text.
    """
    documents = _with_baselines(_documents_to_read(paths, stdin_filename=stdin_filename), since)
    from_stdin = stdin_filename is not None
    if from_stdin and write:
        _usage_error('--write has no file to write when the draft comes from stdin.')

    fixer = Fixer(_build_linter(), _external_linters(delegate))
    changed_file_count = 0
    unresolved_finding_count = 0
    for document in documents:
        fix_result = fixer.run(document, _rules_for(document))
        unresolved_finding_count += len(fix_result.unresolved_findings)
        if from_stdin:
            typer.echo(fix_result.document.text, nl=False)
        if fix_result.has_changes:
            changed_file_count += 1
            if write:
                pathlib.Path(_file_path(document)).write_text(fix_result.document.text, encoding='utf-8')
            elif not from_stdin:
                typer.echo(_diff(document, fix_result.document))
        if fix_result.unresolved_findings:
            typer.echo(reporters.brief(fix_result.document, fix_result.report), err=from_stdin)
        if fix_result.report.advisory:
            typer.echo(reporters.advice(fix_result.document, fix_result.report), err=from_stdin)

    # A draft from stdin comes back rewritten on stdout, as a file does with --write.
    action_word = 'rewrote' if write or from_stdin else 'would rewrite'
    typer.echo(
        f'{action_word} {changed_file_count} of {len(documents)} {"file" if len(documents) == 1 else "files"}, '
        f'{unresolved_finding_count} {"finding needs" if unresolved_finding_count == 1 else "findings need"} an author.',
        err=True,
    )
    raise typer.Exit(1 if unresolved_finding_count else 0)


@app.command()
def stats(
    paths: list[pathlib.Path] = typer.Argument(..., help='Files or directories to measure.'),
    commits: int = typer.Option(
        0, '--commits', min=0, help='Also measure the messages of this many recent commits in the repository.'
    ),
    output: str = typer.Option('text', '--output', help='text or json.'),
) -> None:
    """Measure the prose of each surface, to set limits from what the repository already holds.

    Each count a rule takes is measured beside the value the project sets for it, under the project's config.
    """
    formatter = _STATISTICS_FORMATTERS.get(output)
    if formatter is None:
        _usage_error(f'Unknown output format {output!r}. Choose text or json.')
    documents = _load(tuple(paths)) + _commit_messages(paths[0], commits)
    _require(documents)
    typer.echo(formatter(CorpusMeter(DEFAULT_PARSER, ALL_RULES).run(documents, _rules_for)))


@app.command()
def rules() -> None:
    """Print the native rules, with the surfaces each one reads."""
    typer.echo(rule_reference.render(ALL_RULES, DEFAULT_PARSER), nl=False)


@app.command(name='install-git-hooks')
def install_git_hooks(
    directory: pathlib.Path = typer.Argument(pathlib.Path('.'), help='A directory inside the repository.'),
) -> None:
    """Install git hooks that lay out the prose a commit changes and its message, and stop on what needs rewriting.

    A hook another tool already holds, or one pre-commit manages, is left alone, with the step to take instead.
    """
    repository = GitRepository.at(directory)
    if repository is None:
        typer.echo(f'{directory} is not inside a git repository.', err=True)
        raise typer.Exit(2)
    try:
        typer.echo(GitHooks(repository, __version__, EXTENSIONS).install())
    except GitHookInstallError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(f'subedit {__version__}')


def main() -> int:
    app()
    return 0


def _rules_for(document: Document) -> RuleSet:
    return _config(DEFAULT_CONFIG_SOURCE.resolve, _file_path(document))


# A config subedit cannot read stops the run, since checking against defaults the project never chose misleads.
def _config(read: typing.Callable[[str], ConfigT], path: str) -> ConfigT:
    try:
        return read(path)
    except ConfigError as error:
        typer.echo(f'subedit: {error}', err=True)
        raise typer.Exit(2) from None


def _usage_error(message: str) -> typing.NoReturn:
    typer.echo(f'subedit: {message}', err=True)
    raise typer.Exit(2)


def _load(paths: tuple[pathlib.Path, ...]) -> tuple[Document, ...]:
    source_paths: list[pathlib.Path] = []
    for path in paths:
        if path.is_dir():
            source_paths.extend(
                sorted(
                    candidate
                    for candidate in path.rglob('*')
                    if language_id_for(candidate) is not None and not _is_written_elsewhere(candidate.relative_to(path))
                )
            )
        elif language_id_for(path) is not None:
            source_paths.append(path)
    documents: list[Document] = []
    for source_path in source_paths:
        if _is_excluded(source_path):
            continue
        try:
            text = source_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        language_id = language_id_for(source_path)
        if language_id is None:
            continue
        documents.append(Document(uri=source_path.resolve().as_uri(), text=text, language_id=language_id))
    return tuple(documents)


def _is_excluded(path: pathlib.Path) -> bool:
    root = _config(DEFAULT_CONFIG_SOURCE.root_for, str(path))
    return DEFAULT_CONFIG_SOURCE.is_excluded(path, root, _config(DEFAULT_CONFIG_SOURCE.exclude_patterns, str(path)))


# Installed packages and tool caches hold code nobody here wrote, such as node_modules or a .venv,
# and a tool writes a lock file whole.
def _is_written_elsewhere(relative: pathlib.Path) -> bool:
    if relative.name in GENERATED_NAMES:
        return True
    return any(part in VENDOR_DIRECTORIES or part.startswith('.') for part in relative.parts[:-1])


# Paths and a draft on stdin are two ways to name the input, so a command takes one.
def _documents_to_read(
    paths: list[pathlib.Path] | None, *, stdin_filename: pathlib.Path | None
) -> tuple[Document, ...]:
    named = tuple(paths or ())
    if not named:
        _usage_error('Name files or directories, or - for a draft on stdin.')
    if _STDIN in named:
        return (_draft_on_stdin(named, stdin_filename),)
    if stdin_filename is not None:
        _usage_error('--stdin-filename names a draft read from stdin, so it needs - as the only path.')
    documents = _load(named)
    # A hook names the files a commit holds, and one the project excludes has nothing to check, which is no mistake.
    if not documents and all(path.is_file() and _is_excluded(path) for path in named):
        raise typer.Exit(0)
    _require(documents)
    return documents


def _draft_on_stdin(paths: tuple[pathlib.Path, ...], stdin_filename: pathlib.Path | None) -> Document:
    if len(paths) > 1:
        _usage_error('- reads one draft from stdin, so it stands alone, with no other paths.')
    if stdin_filename is None:
        _usage_error('- needs --stdin-filename to name the file the draft stands for, such as issue.md.')
    language_id = language_id_for(stdin_filename)
    if language_id is None:
        _usage_error(
            f'subedit reads no {stdin_filename.suffix or "extensionless"} files, so name a draft such as issue.md.'
        )
    return Document(uri=stdin_filename.resolve().as_uri(), text=sys.stdin.read(), language_id=language_id)


def _with_baselines(documents: tuple[Document, ...], since: str | None) -> tuple[Document, ...]:
    if since is None:
        return documents
    source = _baseline_source(since, documents)
    return tuple(
        dataclasses.replace(document, baseline=source.baseline_for(pathlib.Path(_file_path(document))))
        for document in documents
    )


# A file and a revision can share a name, as a file called HEAD would, so a name that is both is refused, as git does.
# ./ marks a file, since no revision starts with a dot, and ^0 marks a commit.
def _baseline_source(since: str, documents: tuple[Document, ...]) -> BaselineSource:
    repository = GitRepository.at(pathlib.Path.cwd())
    revision_source = _revision_source(repository, since)
    named_file = pathlib.Path(since)
    if named_file.is_file() and revision_source is not None:
        _usage_error(
            f'--since {since} names both a file and a git revision. '
            f'Write ./{named_file.as_posix()} for the file, or {since}^0 for the commit.'
        )
    if revision_source is not None:
        return revision_source
    if named_file.is_file():
        if len(documents) != 1:
            _usage_error('--since a file compares one file or draft with it, so it takes a single input.')
        try:
            return FileBaselineSource(named_file.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError):
            _usage_error(f'--since cannot read {since}.')
    if repository is None:
        _usage_error(f'--since {since} names no file, and outside a git repository it names no revision either.')
    _usage_error(
        f'--since {since} names no file and no commit git knows. '
        'Name a file, such as ./old.md, or a revision, such as HEAD or a branch.'
    )


# HEAD names the last commit, and in a repository with none yet, a start before every file.
def _revision_source(repository: GitRepository | None, since: str) -> GitRevisionBaselineSource | None:
    if repository is None:
        return None
    if since == 'HEAD':
        return GitRevisionBaselineSource.at_head(repository)
    commit = repository.commit_named(since)
    return GitRevisionBaselineSource(repository, commit) if commit is not None else None


def _commit_messages(path: pathlib.Path, count: int) -> tuple[Document, ...]:
    if not count:
        return ()
    repository = GitRepository.at(path if path.is_dir() else path.parent)
    if repository is None:
        _usage_error(f'--commits reads the history of a git repository, and {path} is in none.')
    message_file = repository.git_path('COMMIT_EDITMSG')
    language_id = language_id_for(message_file)
    if language_id is None:
        return ()
    return tuple(
        Document(uri=message_file.as_uri(), text=message, language_id=language_id)
        for message in repository.commit_messages(count)
    )


def _require(documents: tuple[Document, ...]) -> None:
    if not documents:
        typer.echo('No readable source files found.', err=True)
        raise typer.Exit(1)


def _build_linter() -> Linter:
    return Linter(DEFAULT_PARSER, RuleEngine(ALL_RULES))


def _build_report_aggregator(delegate: bool) -> ReportAggregator:
    return ReportAggregator(_build_linter(), _external_linters(delegate))


# A command can wait for a download, unlike the hook, and a skipped tool must not read as a clean run.
def _external_linters(delegate: bool) -> tuple[ExternalLinter, ...]:
    if not delegate:
        return ()
    for external_linter in EXTERNAL_LINTERS:
        external_linter.prepare()
        if not external_linter.is_available():
            typer.echo(
                f'{external_linter.name} is not installed, so its checks were skipped. '
                'Install subedit[vale] for Vale, or pass --no-delegate to skip it on purpose.',
                err=True,
            )
    return EXTERNAL_LINTERS


def _file_path(document: Document) -> str:
    return document.uri.removeprefix('file://')


def _diff(before: Document, after: Document) -> str:
    path = _file_path(before)
    return ''.join(
        difflib.unified_diff(
            source_lines(before.text),
            source_lines(after.text),
            fromfile=path,
            tofile=path,
        )
    ).rstrip('\n')


if __name__ == '__main__':
    sys.exit(main())
