import dataclasses
import typing

from .diagnostic import RuleMetadata, Severity


# Black and ruff format Python to this width unless a project says otherwise.
DEFAULT_LINE_WIDTH = 120


@dataclasses.dataclass(frozen=True, slots=True)
class RuleSettings:
    severity: Severity | None = None
    options: typing.Mapping[str, object] = dataclasses.field(default_factory=dict)

    def integer(self, name: str, fallback: int) -> int:
        option = self.options.get(name, fallback)
        return option if isinstance(option, int) and not isinstance(option, bool) else fallback


@dataclasses.dataclass(frozen=True, slots=True)
class RuleSet:
    enabled_rule_ids: frozenset[str]
    settings: typing.Mapping[str, RuleSettings] = dataclasses.field(default_factory=dict)
    line_width: int = DEFAULT_LINE_WIDTH
    # A delegated tool's rules are not known up front, so they are listed when switched off instead.
    disabled_external_ids: frozenset[str] = frozenset()

    def is_enabled(self, rule_id: str) -> bool:
        return rule_id in self.enabled_rule_ids

    def settings_for(self, rule_id: str) -> RuleSettings:
        return self.settings.get(rule_id, RuleSettings())

    def severity_for(self, metadata: RuleMetadata) -> Severity:
        return self.settings_for(metadata.rule_id).severity or metadata.default_severity

    def allows_external(self, rule_id: str) -> bool:
        return rule_id not in self.disabled_external_ids
