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
    """What a rule may read besides the unit, which is the document and the rule set."""

    document: Document
    rule_set: RuleSet

    def settings(self, rule_id: str) -> RuleSettings:
        return self.rule_set.settings_for(rule_id)


class Rule(abc.ABC, typing.Generic[UnitT]):
    """A check on one surface, which reports findings on each unit it reads and never edits text itself."""

    metadata: RuleMetadata
    # The kind of unit the rule reads,
    # so a comment rule never meets a heading and a Markdown rule never meets a docstring.
    surface: type[UnitT]
    # A rule on where a unit sits in its file, which a fragment such as a Markdown code block has no part in.
    reads_whole_file: bool = False

    def reads(self, unit: ProseUnit) -> typing.TypeGuard[UnitT]:
        return isinstance(unit, self.surface)

    @abc.abstractmethod
    def check(self, unit: UnitT, context: RuleContext) -> typing.Iterable[Diagnostic]: ...
