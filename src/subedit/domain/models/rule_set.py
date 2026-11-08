import dataclasses
import typing

from .diagnostic import RuleMetadata, Severity
from .rule_option import OptionT, RuleOption


# Black and ruff format Python to this width unless a project says otherwise.
DEFAULT_LINE_WIDTH = 120


@dataclasses.dataclass(frozen=True, slots=True)
class RuleSettings:
    """One rule's severity, when the project overrides it, and its options."""

    severity: Severity | None = None
    options: typing.Mapping[str, object] = dataclasses.field(default_factory=dict)

    def value(self, option: RuleOption[OptionT]) -> OptionT:
        """The project's value for an option, which the config source has checked against its default's type."""
        return typing.cast(OptionT, self.options.get(option.name, option.default))


@dataclasses.dataclass(frozen=True, slots=True)
class RuleSet:
    """Which rules a project runs, at what width, and with what settings."""

    enabled_rule_ids: frozenset[str]
    settings: typing.Mapping[str, RuleSettings] = dataclasses.field(default_factory=dict)
    line_width: int = DEFAULT_LINE_WIDTH
    # A delegated tool's rules are not known up front, so they are listed when switched off instead.
    disabled_external_ids: frozenset[str] = frozenset()
    # A document embedded in another, such as a Markdown code block, is often an example,
    # so a project opts in to having it read.
    reads_embedded: bool = False
    # Abbreviations the project adds to the built-in ones, each with its period, such as Dept.
    abbreviations: frozenset[str] = frozenset()
    # The rule set of each language whose surface the project sets apart, by its language id,
    # which holds the project's rules for every surface with the surface's own laid over them.
    by_language: typing.Mapping[str, 'RuleSet'] = dataclasses.field(default_factory=dict)

    def for_language(self, language_id: str) -> 'RuleSet':
        """The rule set a document in a language is checked under, its surface's own where the project sets one."""
        return self.by_language.get(language_id, self)

    def is_enabled(self, rule_id: str) -> bool:
        return rule_id in self.enabled_rule_ids

    def settings_for(self, rule_id: str) -> RuleSettings:
        return self.settings.get(rule_id, RuleSettings())

    def severity_for(self, metadata: RuleMetadata) -> Severity:
        return self.settings_for(metadata.rule_id).severity or metadata.default_severity

    def allows_external(self, rule_id: str) -> bool:
        return rule_id not in self.disabled_external_ids
