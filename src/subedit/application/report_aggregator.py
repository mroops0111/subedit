import dataclasses

from ..domain.models.diagnostic import Diagnostic, Report
from ..domain.models.document import Document
from ..domain.models.rule_set import RuleSet
from ..domain.ports.external_linter import ExternalLinter
from .linter import Linter


class ReportAggregator:
    """Joins the native report with what each outside checker finds in prose, as the project configures it."""

    def __init__(self, linter: Linter, external_linters: tuple[ExternalLinter, ...] = ()) -> None:
        self._linter = linter
        self._external_linters = external_linters

    def run(self, document: Document, rule_set: RuleSet) -> Report:
        inspection = self._linter.inspect(document, rule_set)
        report = inspection.report
        missing_sources: list[str] = []
        for external_linter in self._external_linters:
            if not external_linter.is_available():
                missing_sources.append(external_linter.name)
                continue
            found = tuple(item for item in external_linter.run(document) if inspection.prose_map.admits(item))
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
