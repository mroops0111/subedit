import abc
import dataclasses
import enum
import typing

from .position import SourceRange
from .text import TextEdit


class Severity(enum.IntEnum):
    """How much a finding weighs, where an error blocks and anything lower reaches the author as advice."""

    SUGGESTION = 1
    WARNING = 2
    ERROR = 3


SEVERITY_BY_NAME = {severity.name.lower(): severity for severity in Severity}


class FixKind(enum.Enum):
    """Who resolves a finding, the fixer for a targeted edit or a reflow, and the author for a rewrite."""

    TARGETED = 'targeted'
    REFLOW = 'reflow'
    REWRITE = 'rewrite'

    @property
    def is_mechanical(self) -> bool:
        return self is not FixKind.REWRITE


@dataclasses.dataclass(frozen=True, slots=True)
class Fix:
    """The edits that resolve a finding, which a rewrite never carries, since only its author can make it."""

    kind: FixKind
    edits: tuple[TextEdit, ...] = ()

    def __post_init__(self) -> None:
        if self.kind is FixKind.REWRITE and self.edits:
            raise ValueError('A REWRITE fix carries no edits, only the author can resolve it')
        if self.kind.is_mechanical and not self.edits:
            raise ValueError(f'A {self.kind.name} fix must carry at least one edit')

    @classmethod
    def targeted(cls, *edits: TextEdit) -> 'Fix':
        return cls(FixKind.TARGETED, edits)

    @classmethod
    def reflow(cls, *edits: TextEdit) -> 'Fix':
        return cls(FixKind.REFLOW, edits)

    @classmethod
    def rewrite(cls) -> 'Fix':
        return cls(FixKind.REWRITE)


OptionT = typing.TypeVar('OptionT')


@dataclasses.dataclass(frozen=True)
class RuleOption(abc.ABC, typing.Generic[OptionT]):
    """A setting a rule takes under its table in the config, with the value it has when the project sets none."""

    name: str
    default: OptionT

    @abc.abstractmethod
    def accepts(self, value: object) -> bool:
        """Whether a value read from the config, where a list arrives as a list, is one this option takes."""

    @property
    @abc.abstractmethod
    def expected(self) -> str:
        """What the option takes, as the end of the sentence a config error states."""


@dataclasses.dataclass(frozen=True)
class CountOption(RuleOption[int]):
    def accepts(self, value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    @property
    def expected(self) -> str:
        return 'a whole number of zero or more'


@dataclasses.dataclass(frozen=True)
class ChoiceOption(RuleOption[str]):
    # The names the option may take, such as the standards a rule can follow.
    choices: tuple[str, ...]

    def accepts(self, value: object) -> bool:
        return value in self.choices

    @property
    def expected(self) -> str:
        return f'one of {", ".join(self.choices)}'


@dataclasses.dataclass(frozen=True)
class WordsOption(RuleOption[tuple[str, ...]]):
    def accepts(self, value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    @property
    def expected(self) -> str:
        return 'a list of strings'


@dataclasses.dataclass(frozen=True)
class HeadingLevelsOption(RuleOption[tuple[int, ...]]):
    def accepts(self, value: object) -> bool:
        return isinstance(value, list) and all(
            isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= 6 for item in value
        )

    @property
    def expected(self) -> str:
        return 'a list of heading levels from 1 to 6'


@dataclasses.dataclass(frozen=True, slots=True)
class RuleMetadata:
    rule_id: str
    summary: str
    fix_kind: FixKind
    default_severity: Severity = Severity.ERROR
    source: str = 'subedit'
    options: tuple[RuleOption[typing.Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError('A rule needs an id')


@dataclasses.dataclass(frozen=True, slots=True)
class Diagnostic:
    rule_id: str
    range: SourceRange
    message: str
    severity: Severity = Severity.ERROR
    fix: Fix | None = None
    source: str = 'subedit'
    # A finding the rule may have read wrong reaches the author as advice, unless the project sets its severity.
    tentative: bool = False

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError(f'Rule {self.rule_id} produced an empty message')

    @property
    def is_mechanical(self) -> bool:
        return self.fix is not None and self.fix.kind.is_mechanical

    @property
    def needs_author(self) -> bool:
        return not self.is_mechanical


@dataclasses.dataclass(frozen=True, slots=True)
class Report:
    """The findings on one document, sorted by who resolves them and whether they block."""

    diagnostics: tuple[Diagnostic, ...] = ()
    unavailable_sources: tuple[str, ...] = ()

    @property
    def mechanical(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.is_mechanical)

    @property
    def needing_author(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.needs_author)

    @property
    def blocking(self) -> tuple[Diagnostic, ...]:
        """The findings an author must resolve, since a warning reaches them as advice and blocks nothing."""
        return tuple(diagnostic for diagnostic in self.needing_author if diagnostic.severity is Severity.ERROR)

    @property
    def advisory(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.needing_author if diagnostic.severity is not Severity.ERROR)

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.severity is Severity.ERROR for diagnostic in self.diagnostics)

    @property
    def is_clean(self) -> bool:
        return not self.diagnostics

    def by_fix_kind(self, wanted: FixKind) -> tuple[Diagnostic, ...]:
        return tuple(
            diagnostic
            for diagnostic in self.diagnostics
            if diagnostic.fix is not None and diagnostic.fix.kind is wanted
        )

    def merged_with(self, other: 'Report') -> 'Report':
        seen_keys: set[tuple[str, int, int, str]] = set()
        merged_diagnostics: list[Diagnostic] = []
        for diagnostic in (*self.diagnostics, *other.diagnostics):
            # One rule can find several sentences in one block, and each finding carries its own message.
            key = (diagnostic.rule_id, diagnostic.range.start, diagnostic.range.end, diagnostic.message)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged_diagnostics.append(diagnostic)
        merged_diagnostics.sort(key=lambda diagnostic: (diagnostic.range.start, diagnostic.rule_id))
        return Report(
            tuple(merged_diagnostics),
            tuple(dict.fromkeys((*self.unavailable_sources, *other.unavailable_sources))),
        )
