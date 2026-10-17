import dataclasses

from ..domain.models.diagnostic import Diagnostic, Report
from ..domain.models.document import Document
from ..domain.models.position import SourceRange
from ..domain.models.rule_set import RuleSet
from ..domain.ports.external_linter import ExternalLinter
from .linter import Linter


class ReportAggregator:
    def __init__(self, linter: Linter, external_linters: tuple[ExternalLinter, ...] = ()) -> None:
        self._linter = linter
        self._external_linters = external_linters

    def run(self, document: Document, rule_set: RuleSet) -> Report:
        report = self._linter.run(document, rule_set)
        missing_sources: list[str] = []
        code_ranges = self._linter.code_ranges(document) if self._external_linters else ()
        prose_lines = self._linter.prose_line_ranges(document) if self._external_linters else ()
        for external_linter in self._external_linters:
            if not external_linter.is_available():
                missing_sources.append(external_linter.name)
                continue
            # A prose checker reads an example's code as prose, so what it finds there is noise.
            # An edit it offers outside a comment line would change code, such as the text of a string.
            found = tuple(
                item
                for item in external_linter.run(document)
                if not _inside(item, code_ranges) and _edits_only_prose(item, prose_lines)
            )
            report = report.merged_with(Report(self._configured(found, rule_set)))
        if missing_sources:
            report = report.merged_with(Report(unavailable_sources=tuple(missing_sources)))
        return report

    # The project's config has the last word on a delegated rule, as it does on a native one.
    def _configured(self, diagnostics: tuple[Diagnostic, ...], rule_set: RuleSet) -> tuple[Diagnostic, ...]:
        configured: list[Diagnostic] = []
        for diagnostic in diagnostics:
            if not rule_set.allows_external(diagnostic.rule_id):
                continue
            severity = rule_set.settings_for(diagnostic.rule_id).severity
            configured.append(dataclasses.replace(diagnostic, severity=severity) if severity else diagnostic)
        return tuple(configured)


def _inside(diagnostic: Diagnostic, code_ranges: tuple[SourceRange, ...]) -> bool:
    return any(code_range.start <= diagnostic.range.start < code_range.end for code_range in code_ranges)


def _edits_only_prose(diagnostic: Diagnostic, prose_lines: tuple[SourceRange, ...]) -> bool:
    if diagnostic.fix is None:
        return True
    return all(
        any(line.start <= edit.range.start and edit.range.end <= line.end for line in prose_lines)
        for edit in diagnostic.fix.edits
    )
