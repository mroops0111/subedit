import dataclasses
import re
import typing

from .prose import is_protected, protected_spans
from .word_classes import ADVERBS, ARTICLES, COORDINATING_CONJUNCTIONS, PREPOSITIONS, SUBORDINATING_CONJUNCTIONS


_WORD = re.compile(r"[A-Za-z][A-Za-z'’]*")
# A token joined to a dot, slash, underscore, or at sign is a name such as a file, a path, or a handle.
_NAME_JOINERS = frozenset('./_@\\')
_RUN = re.compile(r'\S+')


@dataclasses.dataclass(frozen=True, slots=True)
class TitleCaseStyle:
    """Which words a Title Case standard leaves lowercase inside a title."""

    minor: frozenset[str]
    # Minor words that may play a role the standard capitalizes, which only syntax tells apart, so they stay as written.
    ambiguous: frozenset[str]


def _short(words: frozenset[str]) -> frozenset[str]:
    return frozenset(word for word in words if len(word) <= 3)


_APA_MINOR = _short(ARTICLES | COORDINATING_CONJUNCTIONS | SUBORDINATING_CONJUNCTIONS | PREPOSITIONS)
# APA lowercases articles, conjunctions, and prepositions of three letters or fewer.
APA = TitleCaseStyle(minor=_APA_MINOR, ambiguous=_APA_MINOR & ADVERBS)
_CHICAGO_MINOR = ARTICLES | frozenset({'and', 'but', 'for', 'nor', 'or'}) | PREPOSITIONS
# Chicago lowercases articles, five coordinating conjunctions, and every preposition, and as in any role,
# while it capitalizes a subordinating conjunction, such as until in Wait Until It Ends.
CHICAGO = TitleCaseStyle(
    minor=_CHICAGO_MINOR,
    ambiguous=_CHICAGO_MINOR & (ADVERBS | (SUBORDINATING_CONJUNCTIONS - {'as'})),
)
TITLE_CASE_STYLES = {'apa': APA, 'chicago': CHICAGO}


def title_case(text: str, keep: tuple[str, ...] = (), style: TitleCaseStyle = APA) -> str:
    """The English words of a title in Title Case, leaving code, names, acronyms, and anything not English alone.

    A word with a capital past its first letter,
    such as OAuth or iOS, keeps its case, and so does a word listed in keep, such as a lowercase name like npm.
    A minor word that may also be an adverb, such as up, keeps the case it was written in.
    """
    kept = {word.lower(): word for word in keep}
    pieces: list[str] = []
    cursor = 0
    for word in _title_words(text):
        pieces.append(text[cursor : word.match.start()])
        pieces.append(_cased(word, kept, style))
        cursor = word.match.end()
    pieces.append(text[cursor:])
    return ''.join(pieces)


def capitalized_ambiguous_words(text: str, style: TitleCaseStyle = APA) -> tuple[str, ...]:
    """The words inside a title written capitalized that the standard lowercases unless they stand as an adverb."""
    return tuple(
        word.match.group()
        for word in _title_words(text)
        if not (word.is_edge or word.in_compound)
        and word.match.group().istitle()
        and word.match.group().lower() in style.ambiguous
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _TitleWord:
    match: re.Match[str]
    # The first word, the last, and the first after a colon are capitalized whatever they are.
    is_edge: bool
    # A word joined by a hyphen, such as on in On-Prem, is part of a compound rather than a preposition.
    in_compound: bool


def _title_words(text: str) -> typing.Iterator[_TitleWord]:
    # A lone lowercase word, such as a package or a field, is more likely a name than a title.
    if len(text.split()) == 1 and text.islower():
        return
    spans = protected_spans(text) + _name_spans(text)
    for match in _WORD.finditer(text):
        if is_protected(match.start(), spans) or text[match.end() : match.end() + 1].isdigit():
            continue
        before = text[: match.start()]
        opens = not any(character.isalnum() for character in before) or before.rstrip().endswith((':', '：'))
        closes = not any(character.isalnum() for character in text[match.end() :])
        in_compound = text[match.start() - 1 : match.start()] == '-' or text[match.end() : match.end() + 1] == '-'
        yield _TitleWord(match, is_edge=opens or closes, in_compound=in_compound)


def _cased(title_word: _TitleWord, kept: dict[str, str], style: TitleCaseStyle) -> str:
    word = title_word.match.group()
    if word.lower() in kept:
        return kept[word.lower()]
    if any(character.isupper() for character in word[1:]):
        return word
    if not title_word.is_edge and word.lower() in style.minor and title_word.in_compound:
        return word
    if not title_word.is_edge and word.lower() in style.ambiguous:
        return word
    if not title_word.is_edge and word.lower() in style.minor:
        return word.lower()
    return word[0].upper() + word[1:]


def _name_spans(text: str) -> tuple[tuple[int, int], ...]:
    """A run of text holding a dot, slash, underscore, or at sign is a name, such as a file, a path, or a package."""
    return tuple((chunk.start(), chunk.end()) for chunk in _RUN.finditer(text) if _NAME_JOINERS & set(chunk.group()))
