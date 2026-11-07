import difflib
import pathlib
import sys
import typing

import typer

from .. import __version__
from ..application import (
    CorpusMeter,
    CorpusStatistics,
    Fixer,
    Linter,
    ReportAggregator,
    RuleEngine,
    SurfaceStatistics,
)
from ..domain.models.document import Document
from ..domain.models.rule_set import RuleSet
from ..domain.models.text import source_lines
from ..domain.ports.external_linter import ExternalLinter
from ..infrastructure import (
    ALL_RULES,
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_PARSER,
    EXTERNAL_LINTERS,
    GENERATED_NAMES,
    VENDOR_DIRECTORIES,
    ConfigError,
    GitHookInstallError,
    GitHooks,
    GitRepository,
    language_id_for,
)
from . import report as reporters
from . import rule_reference


app = typer.Typer(
    add_completion=False, help='A subeditor for AI agents, keeping every sentence they write to your house style.'
)

_FORMATTERS = {
    'full': reporters.full,
    'actionable': reporters.actionable,
    'json': reporters.as_json,
}
_PERCENTILES = (0.5, 0.75, 0.9, 0.95, 0.99)
# A path of - reads one draft from stdin, as ruff, Prettier, and ESLint take it.
_STDIN = pathlib.Path('-')
_STDIN_FILENAME = typer.Option(
    None, '--stdin-filename', help='The file a draft read from stdin stands for, which picks its surface and config.'
)

ConfigT = typing.TypeVar('ConfigT')


@app.command()
def check(
    paths: list[pathlib.Path] = typer.Argument(None, help='Files or directories to check, or - for a draft on stdin.'),
    output: str = typer.Option('full', '--output', help='full, actionable, or json.'),
    delegate: bool = typer.Option(True, '--delegate/--no-delegate', help='Also run Vale and AutoCorrect.'),
    stdin_filename: pathlib.Path | None = _STDIN_FILENAME,
    staged: bool = typer.Option(False, '--staged', help='Check the files git has staged, in place of paths.'),
) -> None:
    """Report findings, and exit non-zero when any is an error."""
    documents = _documents_to_read(paths, stdin_filename=stdin_filename, staged=staged)
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
    staged: bool = typer.Option(
        False, '--staged', help='Fix the files git has staged, in place of paths, and fail when any changed.'
    ),
) -> None:
    """Apply mechanical fixes, printing a diff unless told to write, and report what needs an author.

    A draft read from stdin comes back fixed on stdout, with the findings on stderr, so a pipe keeps only the text.
    """
    documents = _documents_to_read(paths, stdin_filename=stdin_filename, staged=staged)
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
    # A fix written over a staged file leaves the commit holding the old text, so it waits for the file to be staged.
    if staged and changed_file_count:
        typer.echo('Stage the laid out files and commit again.', err=True)
        raise typer.Exit(1)
    raise typer.Exit(1 if unresolved_finding_count else 0)


@app.command()
def stats(paths: list[pathlib.Path] = typer.Argument(..., help='Files or directories to measure.')) -> None:
    """Measure the prose of each surface, to set limits from what the codebase already holds."""
    documents = _load(tuple(paths))
    _require(documents)
    typer.echo(_render(CorpusMeter(DEFAULT_PARSER).run(documents)))


@app.command()
def rules() -> None:
    """Print the native rules, with the surfaces each one reads."""
    typer.echo(rule_reference.render(ALL_RULES, DEFAULT_PARSER), nl=False)


@app.command(name='install-git-hooks')
def install_git_hooks(
    directory: pathlib.Path = typer.Argument(pathlib.Path('.'), help='A directory inside the repository.'),
) -> None:
    """Install git hooks that lay out the staged files and the commit message, and stop on what needs rewriting.

    A hook another tool already holds, or one pre-commit manages, is left alone, with the step to take instead.
    """
    repository = GitRepository.at(directory)
    if repository is None:
        typer.echo(f'{directory} is not inside a git repository.', err=True)
        raise typer.Exit(2)
    try:
        typer.echo(GitHooks(repository, __version__).install())
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
        root = _config(DEFAULT_CONFIG_SOURCE.root_for, str(source_path))
        if DEFAULT_CONFIG_SOURCE.is_excluded(
            source_path, root, _config(DEFAULT_CONFIG_SOURCE.exclude_patterns, str(source_path))
        ):
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


# Installed packages and tool caches hold code nobody here wrote, such as node_modules or a .venv,
# and a tool writes a lock file whole.
def _is_written_elsewhere(relative: pathlib.Path) -> bool:
    if relative.name in GENERATED_NAMES:
        return True
    return any(part in VENDOR_DIRECTORIES or part.startswith('.') for part in relative.parts[:-1])


# A commit that stages no file subedit reads has nothing to check, which is no mistake.
# Paths, a draft on stdin, and what git staged are three ways to name the input, so a command takes one.
def _documents_to_read(
    paths: list[pathlib.Path] | None, *, stdin_filename: pathlib.Path | None, staged: bool
) -> tuple[Document, ...]:
    named = tuple(paths or ())
    if staged:
        if named or stdin_filename is not None:
            _usage_error('--staged reads the files git has staged, so it takes no paths and no --stdin-filename.')
        repository = GitRepository.at(pathlib.Path.cwd())
        if repository is None:
            _usage_error('--staged needs a git repository.')
        documents = _load(repository.staged_files())
        if not documents:
            raise typer.Exit(0)
        return documents
    if not named:
        _usage_error('Name files or directories, - for a draft on stdin, or pass --staged.')
    if _STDIN in named:
        return (_draft_on_stdin(named, stdin_filename),)
    if stdin_filename is not None:
        _usage_error('--stdin-filename names a draft read from stdin, so it needs - as the only path.')
    documents = _load(named)
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


def _render(statistics: CorpusStatistics) -> str:
    return '\n\n'.join(_render_surface(measured) for measured in statistics.surfaces)


def _render_surface(measured: SurfaceStatistics) -> str:
    heading = (
        f'{"group":24s} {"n":>6s} {"med":>5s} '
        + ' '.join(f'p{int(fraction * 100):<3d}' for fraction in _PERCENTILES)
        + '  max'
    )
    lines = [f'{measured.surface}: {measured.document_count} documents, {measured.unit_count} units']
    if measured.line_counts:
        lines.extend(['', 'unit line counts', heading])
        lines.extend(_row(distribution.label, distribution) for distribution in measured.line_counts)
    distributions = (measured.physical_widths, measured.sentence_lengths)
    for distribution in (distribution for distribution in distributions if distribution.count):
        lines.extend(['', distribution.label, _row('', distribution)])
    lines.extend(['', 'sentences over width with no comma to break at'])
    for width, sentence_count in measured.unbreakable_counts_by_width:
        sentence_total = measured.sentence_lengths.count
        percentage = sentence_count / sentence_total * 100 if sentence_total else 0.0
        lines.append(f'  width {width:3d}  {sentence_count:5d} sentences  {percentage:5.2f}%')
    return '\n'.join(lines)


def _row(label: str, distribution: typing.Any) -> str:
    cells = ' '.join(f'{distribution.percentile(fraction):<4d}' for fraction in _PERCENTILES)
    return f'{label:24s} {distribution.count:6d} {distribution.median:5d} {cells} {distribution.maximum:4d}'


if __name__ == '__main__':
    sys.exit(main())
