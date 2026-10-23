import difflib
import pathlib
import sys
import typing

import typer

from .. import __version__
from ..application import CorpusMeter, CorpusStatistics, Fixer, Linter, ReportAggregator, RuleEngine
from ..domain.models.document import Document
from ..domain.models.text import source_lines
from ..domain.ports.external_linter import ExternalLinter
from ..infrastructure import (
    ALL_RULES,
    DEFAULT_CONFIG_SOURCE,
    DEFAULT_PARSER,
    EXTENSIONS,
    EXTERNAL_LINTERS,
    VENDOR_DIRECTORIES,
    language_for,
)
from . import report as reporters
from . import rule_reference


app = typer.Typer(
    add_completion=False, help='A subeditor for AI agents, keeping every sentence they write to your house style.'
)

FORMATTERS = {
    'full': reporters.full,
    'actionable': reporters.actionable,
    'json': reporters.as_json,
}
PERCENTILES = (0.5, 0.75, 0.9, 0.95, 0.99)


@app.command()
def check(
    paths: list[pathlib.Path] = typer.Argument(..., help='Files or directories to check.'),
    output: str = typer.Option('full', '--output', help='full, actionable, or json.'),
    delegate: bool = typer.Option(True, '--delegate/--no-delegate', help='Also run Vale and AutoCorrect.'),
) -> None:
    documents = _load(tuple(paths))
    _require(documents)
    formatter = FORMATTERS.get(output)
    if formatter is None:
        typer.echo(f'Unknown output format {output!r}. Choose full, actionable, or json.', err=True)
        raise typer.Exit(2)

    aggregator = _build_report_aggregator(delegate)
    has_errors = False
    for document in documents:
        report = aggregator.run(document, DEFAULT_CONFIG_SOURCE.resolve(_file_path(document)))
        has_errors = has_errors or report.has_errors
        rendered_report = formatter(document, report)
        if rendered_report:
            typer.echo(rendered_report)
    raise typer.Exit(1 if has_errors else 0)


@app.command()
def fix(
    paths: list[pathlib.Path] = typer.Argument(..., help='Files or directories to fix.'),
    write: bool = typer.Option(False, '--write', help='Write changes instead of printing a diff.'),
    delegate: bool = typer.Option(True, '--delegate/--no-delegate', help='Also run Vale and AutoCorrect.'),
) -> None:
    documents = _load(tuple(paths))
    _require(documents)

    fixer = Fixer(_build_linter(), _external_linters(delegate))
    changed_file_count = 0
    unresolved_finding_count = 0
    for document in documents:
        fix_result = fixer.run(document, DEFAULT_CONFIG_SOURCE.resolve(_file_path(document)))
        unresolved_finding_count += len(fix_result.unresolved_findings)
        if fix_result.has_changes:
            changed_file_count += 1
            if write:
                pathlib.Path(_file_path(document)).write_text(fix_result.document.text, encoding='utf-8')
            else:
                typer.echo(_diff(document, fix_result.document))
        if fix_result.unresolved_findings:
            typer.echo(reporters.brief(fix_result.document, fix_result.report))
        if fix_result.report.advisory:
            typer.echo(reporters.advice(fix_result.document, fix_result.report))

    action_word = 'rewrote' if write else 'would rewrite'
    typer.echo(
        f'{action_word} {changed_file_count} of {len(documents)} files, {unresolved_finding_count} findings need an author.',
        err=True,
    )
    raise typer.Exit(1 if unresolved_finding_count else 0)


@app.command()
def stats(paths: list[pathlib.Path] = typer.Argument(..., help='Files or directories to measure.')) -> None:
    documents = _load(tuple(paths))
    _require(documents)
    typer.echo(_render(CorpusMeter(DEFAULT_PARSER).run(documents)))


@app.command()
def rules(
    destination: pathlib.Path = typer.Option(None, '--write', help='Write the generated table to this path.'),
) -> None:
    rule_table = rule_reference.render(ALL_RULES)
    if destination is None:
        typer.echo(rule_table, nl=False)
        return
    destination.write_text(rule_table, encoding='utf-8')


@app.command()
def version() -> None:
    typer.echo(f'subedit {__version__}')


def main() -> int:
    app()
    return 0


def _load(paths: tuple[pathlib.Path, ...]) -> tuple[Document, ...]:
    source_paths: list[pathlib.Path] = []
    for path in paths:
        if path.is_dir():
            source_paths.extend(
                sorted(
                    candidate
                    for candidate in path.rglob('*')
                    if candidate.suffix in EXTENSIONS and not _is_vendored(candidate.relative_to(path))
                )
            )
        elif path.suffix in EXTENSIONS:
            source_paths.append(path)
    documents: list[Document] = []
    for source_path in source_paths:
        root = DEFAULT_CONFIG_SOURCE.root_for(str(source_path))
        if DEFAULT_CONFIG_SOURCE.is_excluded(
            source_path, root, DEFAULT_CONFIG_SOURCE.exclude_patterns(str(source_path))
        ):
            continue
        try:
            text = source_path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        language = language_for(source_path)
        if language is None:
            continue
        documents.append(Document(uri=source_path.resolve().as_uri(), text=text, language_id=language.language_id))
    return tuple(documents)


# Installed packages and tool caches hold code nobody here wrote, such as node_modules or a .venv.
def _is_vendored(relative: pathlib.Path) -> bool:
    return any(part in VENDOR_DIRECTORIES or part.startswith('.') for part in relative.parts[:-1])


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
    heading = (
        f'{"group":24s} {"n":>6s} {"med":>5s} '
        + ' '.join(f'p{int(fraction * 100):<3d}' for fraction in PERCENTILES)
        + '  max'
    )
    lines = [
        f'{statistics.document_count} documents, {statistics.group_count} comment blocks',
        '',
        'block line counts',
        heading,
    ]
    lines.extend(_row(distribution.label, distribution) for distribution in statistics.line_counts)
    for distribution in (statistics.physical_widths, statistics.sentence_lengths):
        lines.extend(['', distribution.label, _row('', distribution)])
    lines.extend(['', 'sentences over width with no comma to break at'])
    for width, sentence_count in statistics.unbreakable_counts_by_width:
        percentage = (
            sentence_count / statistics.sentence_lengths.count * 100 if statistics.sentence_lengths.count else 0.0
        )
        lines.append(f'  width {width:3d}  {sentence_count:5d} sentences  {percentage:5.2f}%')
    return '\n'.join(lines)


def _row(label: str, distribution: typing.Any) -> str:
    cells = ' '.join(f'{distribution.percentile(fraction):<4d}' for fraction in PERCENTILES)
    return f'{label:24s} {distribution.count:6d} {distribution.median:5d} {cells} {distribution.maximum:4d}'


if __name__ == '__main__':
    sys.exit(main())
