import json

from ..domain.models.diagnostic import Diagnostic, Report
from ..domain.models.document import Document


def full(document: Document, report: Report) -> str:
    """One line per finding, with its location, severity, rule, and message."""
    if report.is_clean:
        return ''
    lines: list[str] = []
    for diagnostic in report.diagnostics:
        position = document.positions.to_position(diagnostic.range.start)
        location = f'{_path(document)}:{position.line + 1}:{position.character + 1}'
        lines.append(f'{location}  {diagnostic.severity.name.lower()}  {diagnostic.rule_id}  {diagnostic.message}')
    return '\n'.join(lines)


def brief(document: Document, report: Report) -> str:
    """The blocking findings, as a message telling an agent what to rewrite, or nothing when none block."""
    if not report.blocking:
        return ''
    return _rewrite_brief(document, report)


def advice(document: Document, report: Report) -> str:
    """The warnings that need an author, as a message an agent may act on or leave."""
    if not report.advisory:
        return ''
    lines = [
        f'{len(report.advisory)} {"warning" if len(report.advisory) == 1 else "warnings"} in {_path(document)}, worth a look but not required.',
        "Each is a judgment call. Rewrite the text where the finding holds, and leave it where the text meets the rule's criteria.",
    ]
    lines.extend(_finding_lines(document, report.advisory))
    return '\n'.join(lines)


def actionable(document: Document, report: Report) -> str:
    """What the author should do next, which is to rewrite, weigh advice, or run fix."""
    if report.blocking:
        return _rewrite_brief(document, report)
    if report.advisory:
        return advice(document, report)
    if report.mechanical:
        mechanical_count = len(report.mechanical)
        return (
            f'Nothing needs rewriting in {_path(document)}. '
            f'{mechanical_count} finding{"s" if mechanical_count != 1 else ""} can be repaired mechanically, '
            'so run fix --write rather than editing by hand.'
        )
    return f'No findings in {_path(document)}.'


def as_json(document: Document, report: Report) -> str:
    """The findings as JSON, with ranges and fix kinds, for a tool to read."""
    return json.dumps(
        {
            'uri': document.uri,
            'diagnostics': [_encode(document, diagnostic) for diagnostic in report.diagnostics],
            'unavailable_sources': list(report.unavailable_sources),
        },
        indent=2,
    )


def _rewrite_brief(document: Document, report: Report) -> str:
    finding_count = len(report.blocking)
    lines = [
        f'{finding_count} {"finding needs" if finding_count == 1 else "findings need"} rewriting in {_path(document)}.',
        'Each states the fix. Apply it in place, do not add a suppression comment.',
        '',
    ]
    lines.extend(_finding_lines(document, report.blocking))
    return '\n'.join(lines)


def _finding_lines(document: Document, diagnostics: tuple[Diagnostic, ...]) -> list[str]:
    lines: list[str] = []
    for diagnostic in diagnostics:
        position = document.positions.to_position(diagnostic.range.start)
        lines.append(f'line {position.line + 1}  [{diagnostic.rule_id}]')
        lines.append(f'  {diagnostic.message}')
    return lines


def _encode(document: Document, diagnostic: Diagnostic) -> dict[str, object]:
    start_position = document.positions.to_position(diagnostic.range.start)
    end_position = document.positions.to_position(diagnostic.range.end)
    return {
        'rule': diagnostic.rule_id,
        'severity': diagnostic.severity.name.lower(),
        'message': diagnostic.message,
        'fixKind': diagnostic.fix.kind.value if diagnostic.fix else None,
        'mechanical': diagnostic.is_mechanical,
        'range': {
            'start': {'line': start_position.line, 'character': start_position.character},
            'end': {'line': end_position.line, 'character': end_position.character},
        },
    }


def _path(document: Document) -> str:
    return document.uri.removeprefix('file://')
