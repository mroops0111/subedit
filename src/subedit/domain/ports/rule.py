import abc
import dataclasses
import typing

from ..models.diagnostic import Diagnostic, RuleMetadata
from ..models.document import Document
from ..models.prose_unit import ProseUnit
from ..models.rule_set import RuleSet, RuleSettings


UnitT = typing.TypeVar('UnitT', bound=ProseUnit)


@dataclasses.dataclass(frozen=True, slots=True)
class RuleContext:
    document: Document
    rule_set: RuleSet

    @property
    def line_width(self) -> int:
        return self.rule_set.line_width

    def settings(self, rule_id: str) -> RuleSettings:
        return self.rule_set.settings_for(rule_id)


class Rule(abc.ABC, typing.Generic[UnitT]):
    metadata: RuleMetadata
    # The kind of unit the rule reads,
    # so a comment rule never meets a heading and a Markdown rule never meets a docstring.
    surface: type[UnitT]

    def reads(self, unit: ProseUnit) -> typing.TypeGuard[UnitT]:
        return isinstance(unit, self.surface)

    @abc.abstractmethod
    def check(self, unit: UnitT, context: RuleContext) -> typing.Iterable[Diagnostic]: ...
