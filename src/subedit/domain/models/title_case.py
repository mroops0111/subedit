import re

from .prose import is_protected, protected_spans


_WORD = re.compile(r"[A-Za-z][A-Za-z'’]*")
# A token joined to a dot, slash, underscore, or at sign is a name such as a file, a path, or a handle.
_NAME_JOINERS = frozenset('./_@\\')
_RUN = re.compile(r'\S+')
# Articles, short prepositions, and coordinating conjunctions stay lowercase inside a title.
_MINOR_WORDS = frozenset(
    {
        'a',
        'an',
        'the',
        'and',
        'or',
        'but',
        'nor',
        'for',
        'so',
        'yet',
        'in',
        'on',
        'of',
        'to',
        'at',
        'by',
        'as',
        'via',
        'per',
        'vs',
    }
)


def title_case(text: str, keep: tuple[str, ...] = ()) -> str:
    """The English words of a title in Title Case, leaving code, names, acronyms, and anything not English alone.

    A word with a capital past its first letter,
    such as OAuth or iOS, keeps its case, and so does a word listed in keep, such as a lowercase name like npm.
    """
    kept = {word.lower(): word for word in keep}
    spans = protected_spans(text) + _name_spans(text)
    # A lone lowercase word, such as a package or a field, is more likely a name than a title.
    if len(text.split()) == 1 and text.islower():
        return text
    words = [
        match
        for match in _WORD.finditer(text)
        if not is_protected(match.start(), spans) and not text[match.end() : match.end() + 1].isdigit()
    ]
    if not words:
        return text
    pieces: list[str] = []
    cursor = 0
    for match in words:
        word = match.group()
        before = text[: match.start()]
        opens = not any(character.isalnum() for character in before) or before.rstrip().endswith((':', '：'))
        closes = not any(character.isalnum() for character in text[match.end() :])
        pieces.append(text[cursor : match.start()])
        pieces.append(_cased(word, kept, opens=opens, closes=closes))
        cursor = match.end()
    pieces.append(text[cursor:])
    return ''.join(pieces)


def _cased(word: str, kept: dict[str, str], *, opens: bool, closes: bool) -> str:
    if word.lower() in kept:
        return kept[word.lower()]
    if any(character.isupper() for character in word[1:]):
        return word
    if word.lower() in _MINOR_WORDS and not (opens or closes):
        return word.lower()
    return word[0].upper() + word[1:]


def _name_spans(text: str) -> tuple[tuple[int, int], ...]:
    """A run of text holding a dot, slash, underscore, or at sign is a name, such as a file, a path, or a package."""
    return tuple((chunk.start(), chunk.end()) for chunk in _RUN.finditer(text) if _NAME_JOINERS & set(chunk.group()))
