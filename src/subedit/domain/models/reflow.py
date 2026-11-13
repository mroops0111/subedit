import dataclasses
import itertools
import re

from .prose import Sentence, enclosed_spans
from .word_classes import (
    APPOSITION_MARKERS,
    ARTICLES,
    CONJUNCTIVE_ADVERBS,
    COORDINATING_CONJUNCTIONS,
    PREPOSITIONS,
    RELATIVE_PRONOUNS,
    SUBORDINATING_CONJUNCTIONS,
)


# Words that open a clause, so a comma before one is where a sentence divides in meaning.
# For is left out, since it opens a phrase as a preposition far more often than a clause.
# As is left out, since it opens an aside such as "as this once did" as often as a clause.
# That is left out, since it also points at a noun, as in "that file".
_CLAUSE_OPENERS = (
    (COORDINATING_CONJUNCTIONS - {'for'})
    | (SUBORDINATING_CONJUNCTIONS - {'as', 'that'})
    | RELATIVE_PRONOUNS
    | CONJUNCTIVE_ADVERBS
)
_LIST_CLOSERS = frozenset({'and', 'or'})
# Words that open a sentence's framing phrase, such as "By default," or "When it fails,", rather than its first item.
_LEAD_IN_WORDS = PREPOSITIONS | SUBORDINATING_CONJUNCTIONS | CONJUNCTIVE_ADVERBS
# Words that open a list, so a break before them falls ahead of its first item rather than inside it.
_LIST_OPENERS = APPOSITION_MARKERS
_OPENER_ENDS = {'that is': (',',)}


@dataclasses.dataclass(frozen=True, slots=True)
class BreakPolicy:
    """What a sentence's breaks avoid besides the width, as the project's rules set it."""

    # No line of a broken sentence runs shorter than this.
    stub_floor: int = 0
    # A piece this short between two commas may be a list item, such as "base URL,", which a break avoids.
    # None leaves lists out of the choice.
    list_item_words: int | None = None
    # The project's own abbreviations, each with its period, which end no sentence reflow lays out.
    abbreviations: frozenset[str] = frozenset()


def reflow_sentence(
    sentence: str, width: int, policy: BreakPolicy = BreakPolicy(), first_width: int | None = None
) -> tuple[str, ...]:
    """Lay a sentence out on as few lines as fit, breaking only at clause commas.

    Among layouts with that fewest count, one that leaves no stub wins, then one whose breaks split no list,
    then one whose breaks each open a clause, then the one with the longest opening line.
    A sentence with a clause too long for any line falls back to filling each line greedily,
    which leaves the overflow where a rewrite finds it.
    """
    opening_width = width if first_width is None else first_width
    if len(sentence) <= opening_width:
        return (sentence,)
    pieces = _comma_pieces(sentence)
    if len(pieces) == 1:
        return (sentence,)
    return _best_layout(pieces, width, opening_width, policy) or _pack(pieces, width)


def break_cost(lines: tuple[str, ...], item_words: int) -> int:
    """Count the breaks in a laid out sentence that split a list.

    A break away from any comma splits a clause rather than a list, which other rules report.
    """
    sentence = ' '.join(lines)
    pieces = _comma_pieces(sentence)
    piece_at = {offset: index + 1 for index, offset in enumerate(_comma_breaks(sentence))}
    line_ends = (end - 1 for end in itertools.accumulate(len(line) + 1 for line in lines[:-1]))
    return sum(
        _splits_a_list(pieces, piece_at[end], item_words)
        for end in line_ends
        if piece_at.get(end, len(pieces)) < len(pieces)
    )


def line_shared_by(lines: tuple[str, ...], sentences: tuple[Sentence, ...]) -> str | None:
    """The line the first sentence shares with the whole sentences after it, if the author wrote one.

    A line filled with several short sentences, each whole, reads as well as one sentence a line,
    so it stays while it fits.
    """
    start = 0
    for line in lines:
        if start == sentences[0].offset:
            end = start + len(line)
            ending_here = [sentence for sentence in sentences[1:] if sentence.end == end]
            return line if ending_here and sentences[0].end < end else None
        start += len(line) + 1
    return None


def occupied_lines(lines: tuple[str, ...], sentence: Sentence) -> tuple[str, ...] | None:
    """The lines a sentence already occupies, when it has them to itself."""
    covering: list[str] = []
    start = 0
    for line in lines:
        end = start + len(line)
        if start < sentence.end and end > sentence.offset:
            if not covering and start != sentence.offset:
                return None
            covering.append(line)
            if end == sentence.end:
                return tuple(covering)
            if end > sentence.end:
                return None
        start = end + 1
    return None


def keeps_given(
    given_lines: tuple[str, ...], best_lines: tuple[str, ...], budgets: tuple[int, int], stub_floor: int
) -> bool:
    """Whether the author's layout of a sentence stays, since it is legal and takes no more lines than the best one.

    Whether a break splits a list is a guess, so it never overrules the author.
    """
    # A colon ending a line in mid sentence is a rewrite finding, so its layout waits for that rewrite.
    if _breaks_at_a_colon(given_lines):
        return _fits(given_lines, budgets)
    return len(given_lines) == len(best_lines) and is_legal(given_lines, budgets, stub_floor)


def is_legal(lines: tuple[str, ...], budgets: tuple[int, int], stub_floor: int) -> bool:
    """Whether a layout fits its budgets, strands no stub, and breaks only at clause commas."""
    if not _fits(lines, budgets):
        return False
    if len(lines) == 1:
        return True
    if strands_stub(lines, stub_floor):
        return False
    breaks = set(_comma_breaks(' '.join(lines)))
    line_ends = itertools.accumulate(len(line) + 1 for line in lines[:-1])
    return all(line_end - 1 in breaks for line_end in line_ends)


def strands_stub(lines: tuple[str, ...], stub_floor: int) -> bool:
    """Whether a layout of several lines leaves one shorter than the stub floor."""
    return len(lines) > 1 and min(map(len, lines)) < stub_floor


def _comma_pieces(sentence: str) -> tuple[str, ...]:
    pieces: list[str] = []
    start = 0
    for offset in _comma_breaks(sentence):
        pieces.append(sentence[start:offset].strip())
        start = offset
    tail = sentence[start:].strip()
    if tail:
        pieces.append(tail)
    return tuple(pieces) if pieces else (sentence,)


def _comma_breaks(sentence: str) -> tuple[int, ...]:
    """Offsets just past each comma that ends a clause, which are the only places a sentence may break.

    A comma inside brackets or a code span separates items of one phrase, so a break there splits the phrase.
    """
    enclosed = enclosed_spans(sentence)
    return tuple(
        comma.start() + 1
        for comma in re.finditer(r',\s+', sentence)
        if not any(start < comma.start() < end for start, end in enclosed)
    )


def _pack(pieces: tuple[str, ...], width: int) -> tuple[str, ...]:
    lines: list[str] = []
    current_line = ''
    for piece in pieces:
        candidate = f'{current_line} {piece}'.strip() if current_line else piece
        if current_line and len(candidate) > width:
            lines.append(current_line)
            current_line = piece
        else:
            current_line = candidate
    if current_line:
        lines.append(current_line)
    return tuple(lines)


def _best_layout(
    pieces: tuple[str, ...], width: int, opening_width: int, policy: BreakPolicy
) -> tuple[str, ...] | None:
    """Pick break points by dynamic programming over the pieces, scoring each layout from the end backwards."""
    count = len(pieces)
    finished: tuple[tuple[int, int, int, int], tuple[str, ...]] = ((0, 0, 0, 0), ())
    best: list[tuple[tuple[int, int, int, int], tuple[str, ...]] | None] = [None] * count
    best.append(finished)
    for start in reversed(range(count)):
        line_width = opening_width if start == 0 else width
        for stop in range(start + 1, count + 1):
            line = ' '.join(pieces[start:stop])
            if len(line) > line_width:
                break
            rest = best[stop]
            if rest is None:
                continue
            (rest_lines, rest_stubs, rest_lists, rest_asides), rest_layout = rest
            is_stub = (start, stop) != (0, count) and len(line) < policy.stub_floor
            splits_list = (
                stop < count
                and policy.list_item_words is not None
                and _splits_a_list(pieces, stop, policy.list_item_words)
            )
            opens_aside = stop < count and not _opens_a_clause(pieces[stop])
            score = (rest_lines + 1, rest_stubs + is_stub, rest_lists + splits_list, rest_asides + opens_aside)
            candidate = (score, (line, *rest_layout))
            current = best[start]
            # On a tie the longer line wins, as filling greedily would choose.
            if current is None or score <= current[0]:
                best[start] = candidate
    found = best[0]
    return None if found is None else found[1]


def serial_item_words(sentence: str) -> tuple[int, ...]:
    """How many words each item of a serial list runs to, as in "a parser, a linter, and a fixer".

    The items are the pieces between two commas ahead of the piece that closes the run on and or or,
    leaving out a piece that opens a clause.
    """
    pieces = _comma_pieces(sentence)
    closers = [index for index, piece in enumerate(pieces) if index >= 2 and _closes_a_run(piece)]
    if not closers:
        return ()
    return tuple(len(pieces[index].split()) for index in range(1, closers[-1]) if not _opens_a_clause(pieces[index]))


def _splits_a_list(pieces: tuple[str, ...], index: int, item_words: int) -> bool:
    """Whether a break before ``pieces[index]`` falls beside an item of a list rather than between clauses."""
    if _opens_a_list(pieces[index]):
        return False
    return (
        _is_list_item(pieces, index - 1, item_words)
        or _is_list_item(pieces, index, item_words)
        or _splits_a_serial_run(pieces, index, item_words)
    )


# A short piece is an item, such as "base URL,", when the run goes on with another short piece or closes on and or or.
# One standing alone, such as "returns ``None``,", or one opening a clause, such as "then optional params,", is not.
def _is_list_item(pieces: tuple[str, ...], index: int, item_words: int) -> bool:
    if not 0 < index < len(pieces) - 1 or not _is_short(pieces[index], item_words) or _opens_a_clause(pieces[index]):
        return False
    if _is_appositive(pieces[index], pieces[index + 1].split()):
        return False
    return (
        _closes_a_run(pieces[index + 1])
        or _is_short(pieces[index + 1], item_words)
        or (index >= 2 and _is_short(pieces[index - 1], item_words))
    )


# In "No auth, a static token, and an OAuth client", a break before the second item or the closer splits the list,
# however long one item runs, as long as another is short enough to read as an item.
def _splits_a_serial_run(pieces: tuple[str, ...], index: int, item_words: int) -> bool:
    for closer in (index, index + 1):
        if not 2 <= closer < len(pieces) or not _closes_a_run(pieces[closer]):
            continue
        items = range(closer - 2, closer)
        if any(_opens_a_clause(pieces[item]) for item in items):
            continue
        if any(_reads_as_item(pieces, item, item_words) for item in items):
            return True
    return False


# A sentence's opening piece may instead lead in, as "However," or "In practice," does.
def _reads_as_item(pieces: tuple[str, ...], index: int, item_words: int) -> bool:
    piece = pieces[index]
    if not _is_short(piece, item_words) or _is_appositive(piece, pieces[index + 1].split()):
        return False
    words = piece.split()
    return index > 0 or (len(words) > 1 and words[0].lower() not in _LEAD_IN_WORDS)


def _closes_a_run(piece: str) -> bool:
    words = piece.split()
    return bool(words) and words[0].lower() in _LIST_CLOSERS


# "``owner``, a ``Person``," renames what came before it,
# unless the next piece runs on in parallel, as in "a cat, a dog".
def _is_appositive(piece: str, following: list[str]) -> bool:
    words = piece.split()
    if not words or words[0].lower() not in ARTICLES:
        return False
    parallel = following[1:] if following and following[0].lower() in _LIST_CLOSERS else following
    return not parallel or parallel[0].lower() not in ARTICLES


def _is_short(piece: str, item_words: int) -> bool:
    return len(piece.split()) <= item_words


def _opens_a_clause(piece: str) -> bool:
    words = piece.split()
    return bool(words) and words[0].lower() in _CLAUSE_OPENERS


# An opener ends at a space or a comma, so likewise opens no list.
# That is renames only when a comma sets it off, as in "that is, the cache", and otherwise opens a clause.
def _opens_a_list(piece: str) -> bool:
    lowered = piece.lower()
    return any(
        lowered.startswith(opener) and lowered[len(opener) : len(opener) + 1] in _OPENER_ENDS.get(opener, (' ', ','))
        for opener in _LIST_OPENERS
    )


def _breaks_at_a_colon(lines: tuple[str, ...]) -> bool:
    return any(line.endswith(':') for line in lines[:-1])


def _fits(lines: tuple[str, ...], budgets: tuple[int, int]) -> bool:
    first_budget, body_budget = budgets
    return all(len(line) <= (first_budget if index == 0 else body_budget) for index, line in enumerate(lines))
