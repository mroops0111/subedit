import dataclasses
import itertools
import re


# Abbreviations whose period does not end a sentence, written without that period.
ABBREVIATIONS = frozenset(
    {
        'e.g',
        'i.e',
        'etc',
        'vs',
        'cf',
        'al',
        'approx',
        'fig',
        'ca',
        'resp',
    }
)

_SENTENCE_END = re.compile(r'[.!?]')
_TRAILING_WORD = re.compile(r'([A-Za-z][A-Za-z.]*)$')
_URL = re.compile(r'\b(?:https?://|www\.)\S+')
# A span opened by two backticks, as reStructuredText writes code, closes on two.
_CODE_RUN = re.compile(r'(`+).+?\1')
_BRACKET_PAIRS = {'(': ')', '[': ']', '{': '}'}
_FENCE = re.compile(r'^\s*(```|~~~)')
_LIST_DELIMITER = re.compile(r'^\s*(?:[0-9]+[.)]|[-*+]|[a-zA-Z][.)])\s')
_LITERAL_DELIMITER = '\\b'
_CLOSING_MARKS = '"\')]}'
_APOSTROPHES = ("'", '\u2019')

# Only before a number, since "No. 5" abbreviates while a trailing no ends its sentence.
NUMBER_ABBREVIATION = 'no'


@dataclasses.dataclass(frozen=True, slots=True)
class Sentence:
    text: str
    offset: int

    @property
    def end(self) -> int:
        return self.offset + len(self.text)


@dataclasses.dataclass(frozen=True, slots=True)
class Segment:
    lines: tuple[str, ...]
    is_literal: bool

    @property
    def text(self) -> str:
        return '\n'.join(self.lines)


@dataclasses.dataclass(frozen=True, slots=True)
class ProseMarkup:
    """What a language writes in its comments besides prose, which reflow leaves as written.

    A tag section, such as JSDoc's from its first @throws on, runs to the end of the comment.
    An example tag's body is code, and so is a line commented out of a language whose statements look like one.
    """

    tag_section: re.Pattern[str] | None = None
    example_tag: str | None = None
    code_line: re.Pattern[str] | None = None

    def opens_tag_section(self, line: str) -> bool:
        return self.tag_section is not None and bool(self.tag_section.match(line))

    def opens_example(self, line: str) -> bool:
        return self.example_tag is not None and line.strip().startswith(self.example_tag)

    def is_code(self, line: str) -> bool:
        return self.code_line is not None and bool(self.code_line.search(line))


PLAIN_MARKUP = ProseMarkup()


@dataclasses.dataclass(frozen=True, slots=True)
class Prose:
    text: str
    markup: ProseMarkup = PLAIN_MARKUP

    @property
    def physical_lines(self) -> tuple[str, ...]:
        return tuple(self.text.split('\n'))

    def segments(self) -> tuple[Segment, ...]:
        segments: list[Segment] = []
        current_lines: list[str] = []
        segment_is_literal = False
        inside_fence = False
        inside_literal_marker = False
        inside_list = False
        inside_tags = False
        inside_code = False

        def flush(next_is_literal: bool) -> None:
            nonlocal current_lines, segment_is_literal
            if current_lines and next_is_literal != segment_is_literal:
                segments.append(Segment(tuple(current_lines), segment_is_literal))
                current_lines = []
            segment_is_literal = next_is_literal

        for line in self.physical_lines:
            stripped_line = line.strip()
            inside_tags = inside_tags or self.markup.opens_tag_section(line)
            if inside_tags:
                flush(next_is_literal=True)
                current_lines.append(line)
                continue
            if _FENCE.match(line):
                inside_fence = not inside_fence
                flush(next_is_literal=True)
                current_lines.append(line)
                continue
            if stripped_line.startswith(_LITERAL_DELIMITER):
                inside_literal_marker = stripped_line == _LITERAL_DELIMITER
                flush(next_is_literal=True)
                current_lines.append(line)
                continue
            if not stripped_line:
                inside_literal_marker = False
                inside_list = False
                inside_code = False
                flush(next_is_literal=inside_fence)
                current_lines.append(line)
                continue
            if self._is_list_item(line):
                inside_list = True
            elif not self._continues_list_item(line, inside_list):
                inside_list = False
            # The indented body under a commented-out opening brace is code too.
            inside_code = self.markup.is_code(line) or (inside_code and line[:1].isspace())
            flush(
                next_is_literal=inside_fence
                or inside_literal_marker
                or inside_list
                or self._is_indented(line)
                or inside_code
            )
            current_lines.append(line)

        if current_lines:
            segments.append(Segment(tuple(current_lines), segment_is_literal))
        return tuple(segments)

    def code_line_indexes(self) -> frozenset[int]:
        """The lines that hold code rather than prose, such as a fenced or indented block or an @example body."""
        indexes: set[int] = set()
        inside_fence = False
        inside_example = False
        for index, line in enumerate(self.physical_lines):
            if self.markup.opens_tag_section(line):
                inside_example = self.markup.opens_example(line)
                continue
            if _FENCE.match(line):
                inside_fence = not inside_fence
                continue
            if line.strip() and (
                inside_example or inside_fence or self._is_indented(line) or self.markup.is_code(line)
            ):
                indexes.add(index)
        return frozenset(indexes)

    def _is_indented(self, line: str) -> bool:
        return line.startswith(('    ', '\t'))

    # A wrapped list item is indented under its marker rather than to a fixed width,
    # so the continuation belongs to the item instead of opening a paragraph.
    def _continues_list_item(self, line: str, inside_list: bool) -> bool:
        return inside_list and line[:1].isspace()

    def _is_list_item(self, line: str) -> bool:
        return bool(_LIST_DELIMITER.match(line))

    @property
    def flattened(self) -> str:
        return ' '.join(
            line.strip()
            for segment in self.segments()
            if not segment.is_literal
            for line in segment.lines
            if line.strip()
        )

    def sentences(self) -> tuple[Sentence, ...]:
        text = self.flattened
        if not text:
            return ()
        protected = self._find_protected_spans(text)
        found_sentences: list[Sentence] = []
        start = 0
        for sentence_end in _SENTENCE_END.finditer(text):
            end = sentence_end.end()
            if end < len(text) and text[end] in _CLOSING_MARKS:
                end += 1
            if self._is_protected(sentence_end.start(), protected):
                continue
            if not self._terminates_a_sentence(text, sentence_end.start()):
                continue
            found_sentences.append(Sentence(text[start:end].strip(), start))
            start = end
            while start < len(text) and text[start] == ' ':
                start += 1
        if start < len(text):
            found_sentences.append(Sentence(text[start:].strip(), start))
        return tuple(sentence for sentence in found_sentences if sentence.text)

    # A period inside brackets, as in an ellipsis closing a list of examples, ends no sentence outside them.
    def _find_protected_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        spans = [(url.start(), url.end()) for url in _URL.finditer(text)]
        spans.extend(_enclosed_spans(text))
        return tuple(spans)

    def _is_protected(self, offset: int, spans: tuple[tuple[int, int], ...]) -> bool:
        return any(start <= offset < end for start, end in spans)

    def _terminates_a_sentence(self, text: str, offset: int) -> bool:
        if text[offset] != '.':
            return self._followed_by_break(text, offset)
        if offset + 1 < len(text) and text[offset + 1].isdigit():
            return False
        trailing_word = _TRAILING_WORD.search(text[:offset])
        # The s of a possessive is no initial, so a sentence closing on a word like API's still ends there.
        if trailing_word and text[: trailing_word.start()].endswith(_APOSTROPHES):
            return self._followed_by_break(text, offset)
        word = trailing_word.group(1).lower().rstrip('.') if trailing_word else ''
        if word in ABBREVIATIONS:
            return False
        if word == NUMBER_ABBREVIATION and text[offset + 1 :].lstrip()[:1].isdigit():
            return False
        if trailing_word and len(trailing_word.group(1).replace('.', '')) == 1:
            return False
        return self._followed_by_break(text, offset)

    def _followed_by_break(self, text: str, offset: int) -> bool:
        rest = text[offset + 1 :]
        if not rest:
            return True
        if rest[0] in _CLOSING_MARKS:
            rest = rest[1:]
        return not rest or rest[0] == ' '


def reflow_sentence(sentence: str, width: int, stub_floor: int = 0, first_width: int | None = None) -> tuple[str, ...]:
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
    return _best_layout(pieces, width, opening_width, stub_floor) or _pack(pieces, width)


def _comma_pieces(sentence: str) -> tuple[str, ...]:
    pieces: list[str] = []
    start = 0
    for offset in comma_breaks(sentence):
        pieces.append(sentence[start:offset].strip())
        start = offset
    tail = sentence[start:].strip()
    if tail:
        pieces.append(tail)
    return tuple(pieces) if pieces else (sentence,)


def code_spans(text: str) -> tuple[tuple[int, int], ...]:
    """The offsets each backtick code span covers, which hold code rather than prose."""
    return tuple((code_span.start(), code_span.end()) for code_span in _CODE_RUN.finditer(text))


def comma_breaks(sentence: str) -> tuple[int, ...]:
    """Offsets just past each comma that ends a clause, which are the only places a sentence may break.

    A comma inside brackets or a code span separates items of one phrase, so a break there splits the phrase.
    """
    enclosed = _enclosed_spans(sentence)
    return tuple(
        comma.start() + 1
        for comma in re.finditer(r',\s+', sentence)
        if not any(start < comma.start() < end for start, end in enclosed)
    )


# Only a matched pair encloses anything, so a stray bracket such as the one in "1)" never swallows the sentence.
def _enclosed_spans(sentence: str) -> tuple[tuple[int, int], ...]:
    spans = list(code_spans(sentence))
    open_brackets: list[tuple[str, int]] = []
    for offset, character in enumerate(sentence):
        if any(start <= offset < end for start, end in spans):
            continue
        if character in _BRACKET_PAIRS:
            open_brackets.append((_BRACKET_PAIRS[character], offset))
        elif open_brackets and character == open_brackets[-1][0]:
            spans.append((open_brackets.pop()[1], offset + 1))
    return tuple(spans)


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


# Words that open a clause, so a comma before one is where a sentence divides in meaning.
# As is left out, since it opens an aside such as "as this once did" as often as a clause.
CLAUSE_OPENERS = frozenset(
    {
        'although',
        'and',
        'because',
        'but',
        'nor',
        'or',
        'otherwise',
        'since',
        'so',
        'then',
        'though',
        'unless',
        'until',
        'whereas',
        'which',
        'while',
        'yet',
    }
)
# A piece this short between two commas is an item in a list, such as "base URL,", not a clause.
LIST_ITEM_WORDS = 3
LIST_CLOSERS = frozenset({'and', 'or'})
ARTICLES = frozenset({'a', 'an', 'the'})
# Prepositions that open a sentence's framing phrase, such as "By default,", rather than its first item.
LEAD_IN_WORDS = frozenset({'after', 'at', 'before', 'by', 'during', 'for', 'from', 'in', 'on', 'once', 'when', 'with'})


def _best_layout(pieces: tuple[str, ...], width: int, opening_width: int, stub_floor: int) -> tuple[str, ...] | None:
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
            is_stub = (start, stop) != (0, count) and len(line) < stub_floor
            splits_list = stop < count and _splits_a_list(pieces, stop)
            opens_aside = stop < count and not _opens_a_clause(pieces[stop])
            score = (rest_lines + 1, rest_stubs + is_stub, rest_lists + splits_list, rest_asides + opens_aside)
            candidate = (score, (line, *rest_layout))
            current = best[start]
            # On a tie the longer line wins, as filling greedily would choose.
            if current is None or score <= current[0]:
                best[start] = candidate
    found = best[0]
    return None if found is None else found[1]


def _splits_a_list(pieces: tuple[str, ...], index: int) -> bool:
    """Whether a break before ``pieces[index]`` falls beside an item of a list rather than between clauses."""
    return _is_list_item(pieces, index - 1) or _is_list_item(pieces, index) or _splits_a_serial_run(pieces, index)


# A short piece is an item, such as "base URL,", when the run goes on with another short piece or closes on and or or.
# One standing alone, such as "returns ``None``,", or one opening a clause, such as "then optional params,", is not.
def _is_list_item(pieces: tuple[str, ...], index: int) -> bool:
    if not 0 < index < len(pieces) - 1 or not _is_short(pieces[index]) or _opens_a_clause(pieces[index]):
        return False
    if _is_appositive(pieces[index], pieces[index + 1].split()):
        return False
    return (
        _closes_a_run(pieces[index + 1])
        or _is_short(pieces[index + 1])
        or (index >= 2 and _is_short(pieces[index - 1]))
    )


# In "No auth, a static token, and an OAuth client", a break before the second item or the closer splits the list,
# however long one item runs, as long as another is short enough to read as an item.
def _splits_a_serial_run(pieces: tuple[str, ...], index: int) -> bool:
    for closer in (index, index + 1):
        if not 2 <= closer < len(pieces) or not _closes_a_run(pieces[closer]):
            continue
        items = range(closer - 2, closer)
        if any(_opens_a_clause(pieces[item]) for item in items):
            continue
        if any(_reads_as_item(pieces, item) for item in items):
            return True
    return False


# A sentence's opening piece may instead lead in, as "However," or "In practice," does.
def _reads_as_item(pieces: tuple[str, ...], index: int) -> bool:
    piece = pieces[index]
    if not _is_short(piece) or _is_appositive(piece, pieces[index + 1].split()):
        return False
    words = piece.split()
    return index > 0 or (len(words) > 1 and words[0].lower() not in LEAD_IN_WORDS)


def _closes_a_run(piece: str) -> bool:
    words = piece.split()
    return bool(words) and words[0].lower() in LIST_CLOSERS


# "``owner``, a ``Person``," renames what came before it,
# unless the next piece runs on in parallel, as in "a cat, a dog".
def _is_appositive(piece: str, following: list[str]) -> bool:
    words = piece.split()
    if not words or words[0].lower() not in ARTICLES:
        return False
    parallel = following[1:] if following and following[0].lower() in LIST_CLOSERS else following
    return not parallel or parallel[0].lower() not in ARTICLES


def _is_short(piece: str) -> bool:
    return len(piece.split()) <= LIST_ITEM_WORDS


def _opens_a_clause(piece: str) -> bool:
    words = piece.split()
    return bool(words) and words[0].lower() in CLAUSE_OPENERS


def break_cost(lines: tuple[str, ...]) -> int:
    """Count the breaks in a laid out sentence that split a list."""
    pieces = _comma_pieces(' '.join(lines))
    piece_ends = itertools.accumulate(len(_comma_pieces(line)) for line in lines[:-1])
    return sum(_splits_a_list(pieces, piece_end) for piece_end in piece_ends)
