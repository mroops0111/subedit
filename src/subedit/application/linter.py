import dataclasses
import typing

from ..domain.models.diagnostic import Diagnostic, Report, Severity
from ..domain.models.document import Document
from ..domain.models.embedded import EmbeddedDocument
from ..domain.models.prose_map import ProseMap
from ..domain.models.prose_unit import ProseUnit
from ..domain.models.rule_set import RuleSet
from ..domain.ports import SourceParser
from ..domain.ports.rule import Rule, RuleContext


class RuleEngine:
    """Runs each enabled rule over the units of the surface it reads, at the severity the project sets for it."""

    def __init__(self, rules: tuple[Rule[typing.Any], ...]) -> None:
        duplicate_ids = self._find_duplicate_ids(rules)
        if duplicate_ids:
            raise ValueError(f'Duplicate rule ids registered: {sorted(duplicate_ids)}')
        self._rules = rules

    def run(
        self, document: Document, units: tuple[ProseUnit, ...], rule_set: RuleSet, *, fragment: bool = False
    ) -> tuple[Diagnostic, ...]:
        """Run the enabled rules, leaving out those on a whole file when the document is a fragment of another."""
        context = RuleContext(document=document, rule_set=rule_set)
        enabled_rules = [
            rule
            for rule in self._rules
            if rule_set.is_enabled(rule.metadata.rule_id) and not (fragment and rule.reads_whole_file)
        ]
        diagnostics: list[Diagnostic] = []
        for unit in units:
            for rule in enabled_rules:
                if not rule.reads(unit):
                    continue
                for diagnostic in rule.check(unit, context):
                    diagnostics.append(self._with_severity(diagnostic, rule, rule_set))
        return tuple(diagnostics)

    def _with_severity(self, diagnostic: Diagnostic, rule: Rule[typing.Any], rule_set: RuleSet) -> Diagnostic:
        configured = rule_set.settings_for(rule.metadata.rule_id).severity
        if configured is not None:
            severity = configured
        elif diagnostic.tentative:
            severity = Severity.WARNING
        else:
            severity = rule.metadata.default_severity
        if diagnostic.severity is severity:
            return diagnostic
        return dataclasses.replace(diagnostic, severity=severity)

    def _find_duplicate_ids(self, rules: tuple[Rule[typing.Any], ...]) -> set[str]:
        seen_ids: set[str] = set()
        duplicate_ids: set[str] = set()
        for rule in rules:
            if rule.metadata.rule_id in seen_ids:
                duplicate_ids.add(rule.metadata.rule_id)
            seen_ids.add(rule.metadata.rule_id)
        return duplicate_ids


@dataclasses.dataclass(frozen=True, slots=True)
class Inspection:
    """What one parse of a document yields, the findings and the map of where its prose lies."""

    report: Report = dataclasses.field(default_factory=Report)
    prose_map: ProseMap = dataclasses.field(default_factory=ProseMap)


class Linter:
    """Parses a document once and runs the rule engine over what the parse found."""

    def __init__(self, parser: SourceParser[ProseUnit], engine: RuleEngine) -> None:
        self._parser = parser
        self._engine = engine

    def run(self, document: Document, rule_set: RuleSet) -> Report:
        return self.inspect(document, rule_set).report

    def inspect(self, document: Document, rule_set: RuleSet) -> Inspection:
        if not self._parser.supports(document.language_id):
            return Inspection()
        parsed = self._parser.read(document)
        diagnostics = self._engine.run(document, parsed.units, rule_set)
        if rule_set.reads_code_blocks:
            diagnostics += tuple(
                finding
                for embedded in parsed.embedded
                for finding in self._embedded_findings(document, embedded, rule_set)
            )
        sorted_diagnostics = sorted(diagnostics, key=lambda item: (item.range.start, item.rule_id))
        prose_map = ProseMap.of_units(parsed.units, parsed.skipped)
        return Inspection(Report(tuple(sorted_diagnostics)), prose_map)

    def _embedded_findings(
        self, host: Document, embedded: EmbeddedDocument, rule_set: RuleSet
    ) -> tuple[Diagnostic, ...]:
        language_id = self._parser.language_named(embedded.language_name)
        # A block in the host's own language is an example of the host, often a deliberately wrong one.
        if language_id is None or language_id == host.language_id:
            return ()
        inner = Document(uri=host.uri, text=embedded.text, language_id=language_id)
        units = self._parser.read(inner).units
        found = self._engine.run(inner, units, rule_set, fragment=True)
        return tuple(embedded.host_diagnostic(finding) for finding in found)
