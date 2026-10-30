import dataclasses

from ..domain.models.diagnostic import Diagnostic, Report
from ..domain.models.document import Document
from ..domain.models.prose_map import ProseMap
from ..domain.models.rule_set import RuleSet
from ..domain.ports.external_linter import ExternalLinter
from .linter import Linter


class ReportAggregator:
    """Joins the native report with what each outside checker finds in prose, as the project configures it."""

    def __init__(self, linter: Linter, external_linters: tuple[ExternalLinter, ...] = ()) -> None:
        self._linter = linter
        self._external_linters = external_linters

    def run(self, document: Document, rule_set: RuleSet) -> Report:
        """Check a document with every rule and checker, and each document it holds the same way, mapped back."""
        return self._run(document, rule_set, fragment=False)

    def _run(self, document: Document, rule_set: RuleSet, *, fragment: bool) -> Report:
        inspection = self._linter.inspect(document, rule_set, fragment=fragment)
        report = inspection.report.merged_with(self._external_report(document, inspection.prose_map, rule_set))
        for held in inspection.held:
            held_report = self._run(held.document, rule_set, fragment=True)
            mapped = tuple(held.placement.host_diagnostic(item) for item in held_report.diagnostics)
            report = report.merged_with(Report(mapped, held_report.unavailable_sources))
        return report

    def _external_report(self, document: Document, prose_map: ProseMap, rule_set: RuleSet) -> Report:
        # A checker keeps only what it finds in prose, so a file with none, such as a lock file, skips them all.
        if not prose_map.prose:
            return Report()
        report = Report()
        missing_sources: list[str] = []
        for external_linter in self._external_linters:
            if not external_linter.is_available():
                missing_sources.append(external_linter.name)
                continue
            found = tuple(item for item in external_linter.run(document) if prose_map.admits(item))
            report = report.merged_with(Report(self._configured(found, rule_set)))
        return report.merged_with(Report(unavailable_sources=tuple(missing_sources)))

    # The project's config has the last word on a delegated rule, as it does on a native one.
    def _configured(self, diagnostics: tuple[Diagnostic, ...], rule_set: RuleSet) -> tuple[Diagnostic, ...]:
        configured: list[Diagnostic] = []
        for diagnostic in diagnostics:
            if not rule_set.allows_external(diagnostic.rule_id):
                continue
            severity = rule_set.settings_for(diagnostic.rule_id).severity
            configured.append(dataclasses.replace(diagnostic, severity=severity) if severity else diagnostic)
        return tuple(configured)
