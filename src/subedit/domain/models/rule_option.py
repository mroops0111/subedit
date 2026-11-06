import abc
import dataclasses
import typing

from .prose import words_pattern


# Markdown and HTML number headings from one to six.
HEADING_LEVELS = range(1, 7)

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

    def convert(self, value: object) -> OptionT:
        """An accepted config value in the type of the default, so a rule always meets the same type."""
        return typing.cast(OptionT, value)


@dataclasses.dataclass(frozen=True)
class CountOption(RuleOption[int]):
    def accepts(self, value: object) -> bool:
        return _is_whole_number(value) and typing.cast(int, value) >= 0

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

    def convert(self, value: object) -> tuple[str, ...]:
        """The list TOML reads, as the tuple the default is."""
        return tuple(typing.cast(list[str], value))


@dataclasses.dataclass(frozen=True)
class ReplacementsOption(RuleOption[typing.Mapping[str, str]]):
    def accepts(self, value: object) -> bool:
        if not isinstance(value, dict):
            return False
        pairs = typing.cast(dict[object, object], value).items()
        if not all(isinstance(word, str) and word and isinstance(new, str) and new for word, new in pairs):
            return False
        # A replacement holding a word the table replaces, as cancel out holds cancel, is replaced again each round.
        replacements = typing.cast(dict[str, str], value)
        replaced = words_pattern(replacements)
        return not any(replaced.search(new) for new in replacements.values())

    @property
    def expected(self) -> str:
        return 'a table of words, each set to a word that holds none of the words it replaces'


@dataclasses.dataclass(frozen=True)
class HeadingLevelsOption(RuleOption[tuple[int, ...]]):
    def accepts(self, value: object) -> bool:
        return isinstance(value, list) and all(
            _is_whole_number(item) and item in HEADING_LEVELS for item in typing.cast(list[object], value)
        )

    @property
    def expected(self) -> str:
        return f'a list of heading levels from {HEADING_LEVELS[0]} to {HEADING_LEVELS[-1]}'

    def convert(self, value: object) -> tuple[int, ...]:
        return tuple(typing.cast(list[int], value))


def _is_whole_number(value: object) -> bool:
    # TOML reads true as a bool, which Python also counts as an int.
    return isinstance(value, int) and not isinstance(value, bool)
