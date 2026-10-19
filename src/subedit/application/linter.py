import dataclasses

from ..domain.models.comment import CommentGroup
from ..domain.models.diagnostic import Diagnostic, Report
from ..domain.models.document import Document
from ..domain.models.prose_map import ProseMap
from ..domain.models.rule_set import RuleSet
from ..domain.ports import SourceParser
from ..domain.ports.rule import Rule, RuleContext


class RuleEngine:
    def __init__(self, rules: tuple[Rule, ...]) -> None:
        duplicate_ids = self._find_duplicate_ids(rules)
        if duplicate_ids:
            raise ValueError(f'Duplicate rule ids registered: {sorted(duplicate_ids)}')
        self._rules = rules

    def run(self, document: Document, groups: tuple[CommentGroup, ...], rule_set: RuleSet) -> tuple[Diagnostic, ...]:
        context = RuleContext(document=document, rule_set=rule_set)
        enabled_rules = [rule for rule in self._rules if rule_set.is_enabled(rule.metadata.rule_id)]
        diagnostics: list[Diagnostic] = []
        for group in groups:
            for rule in enabled_rules:
                for diagnostic in rule.check(group, context):
                    diagnostics.append(self._with_severity(diagnostic, rule, rule_set))
        return tuple(diagnostics)

    def _with_severity(self, diagnostic: Diagnostic, rule: Rule, rule_set: RuleSet) -> Diagnostic:
        severity = rule_set.severity_for(rule.metadata)
        if diagnostic.severity is severity:
            return diagnostic
        return dataclasses.replace(diagnostic, severity=severity)

    def _find_duplicate_ids(self, rules: tuple[Rule, ...]) -> set[str]:
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
    def __init__(self, parser: SourceParser, engine: RuleEngine) -> None:
        self._parser = parser
        self._engine = engine

    def run(self, document: Document, rule_set: RuleSet) -> Report:
        return self.inspect(document, rule_set).report

    def inspect(self, document: Document, rule_set: RuleSet) -> Inspection:
        if not self._parser.supports(document.language_id):
            return Inspection()
        groups = self._parser.parse(document)
        diagnostics = self._engine.run(document, groups, rule_set)
        sorted_diagnostics = sorted(diagnostics, key=lambda item: (item.range.start, item.rule_id))
        return Inspection(Report(tuple(sorted_diagnostics)), ProseMap.of_comments(groups))
