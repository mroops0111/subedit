import dataclasses
import re
import typing
import unicodedata


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
# A colon ends a lead-in as a period ends a sentence, so the line after either opens something new.
_ENDS_A_SENTENCE = re.compile(r'[.!?:]["\')\]]*\s*$')
_TRAILING_WORD = re.compile(r'([A-Za-z][A-Za-z.]*)$')
_URL = re.compile(r'\b(?:https?://|www\.)\S+')
# A span opened by two backticks, as reStructuredText writes code, closes on two.
_CODE_RUN = re.compile(r'(`+).+?\1')
# A rule reading prose steps over code, a URL, an image's alt text, a link target, an autolink, and quoted words.
# The code run comes first, since its backreference counts on being the first group.
_PROTECTED = re.compile(
    '|'.join(
        (
            _CODE_RUN.pattern,
            _URL.pattern,
            r'!\[[^\]]*\]',
            r'\]\([^)]*\)',
            r'<[^>\s]+>',
            r'"[^"]*"',
            '“[^”]*”',
            '「[^」]*」',
        )
    )
)
_BRACKET_PAIRS = {'(': ')', '[': ']', '{': '}'}
_FENCE = re.compile(r'^\s*(```|~~~)')
_LITERAL_DELIMITER = '\\b'
_CLOSING_MARKS = '"\')]}'
_OPENING_MARKS = '"\'([{'
_APOSTROPHES = ("'", '\u2019')

# Only before a number, since "No. 5" abbreviates while a trailing no ends its sentence.
NUMBER_ABBREVIATION = 'no'
# A numbered, bulleted, or lettered list item's marker, with the space after it.
LIST_MARKER = re.compile(r'(?:[0-9]+[.)]|[-*+]|[a-zA-Z][.)])\s+')


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
    An example tag's body is code, and so is a line that the language's grammar reads as code commented out.
    """

    tag_section: re.Pattern[str] | None = None
    example_tag: str | None = None
    code_line: typing.Callable[[str], bool] | None = None

    def opens_tag_section(self, line: str) -> bool:
        return self.tag_section is not None and bool(self.tag_section.match(line))

    def opens_example(self, line: str) -> bool:
        return self.example_tag is not None and line.strip().startswith(self.example_tag)

    def is_code(self, line: str) -> bool:
        return self.code_line is not None and self.code_line(line)


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

        lines = self.physical_lines
        for previous_line, line in zip(('', *lines), lines, strict=False):
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
            elif not self._continues_list_item(line, previous_line, inside_list):
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

    # A line set two spaces past the margin, such as a tree diagram or an aligned table, is laid out by hand.
    # Markdown wants four for a code block, but a comment's prefix already takes the space a writer would count.
    def _is_indented(self, line: str) -> bool:
        return line.startswith(('  ', '\t'))

    # A wrapped list item is indented under its marker, or left at the margin while its sentence runs on,
    # so the continuation belongs to the item instead of opening a paragraph.
    def _continues_list_item(self, line: str, previous_line: str, inside_list: bool) -> bool:
        return inside_list and (line[:1].isspace() or not _ENDS_A_SENTENCE.search(previous_line))

    def _is_list_item(self, line: str) -> bool:
        return bool(LIST_MARKER.match(line.lstrip()))

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
        sheltered = self._sheltered_spans(text)
        found_sentences: list[Sentence] = []
        start = 0
        for sentence_end in _SENTENCE_END.finditer(text):
            end = sentence_end.end()
            if end < len(text) and text[end] in _CLOSING_MARKS:
                end += 1
            if is_protected(sentence_end.start(), sheltered):
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
    def _sheltered_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        spans = [(url.start(), url.end()) for url in _URL.finditer(text)]
        spans.extend(enclosed_spans(text))
        return tuple(spans)

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
        if (
            trailing_word
            and len(trailing_word.group(1).replace('.', '')) == 1
            and self._stands_alone(text, trailing_word)
        ):
            return False
        return self._followed_by_break(text, offset)

    # An initial stands as a word of its own, so a letter closing Ctrl+C or a plural such as `Event`s is none.
    def _stands_alone(self, text: str, trailing_word: re.Match[str]) -> bool:
        before = text[: trailing_word.start()]
        return not before or before[-1].isspace() or before[-1] in _OPENING_MARKS

    def _followed_by_break(self, text: str, offset: int) -> bool:
        rest = text[offset + 1 :]
        if not rest:
            return True
        if rest[0] in _CLOSING_MARKS:
            rest = rest[1:]
        return not rest or rest[0] == ' '


def code_spans(text: str) -> tuple[tuple[int, int], ...]:
    """The offsets each backtick code span covers, which hold code rather than prose."""
    return tuple((code_span.start(), code_span.end()) for code_span in _CODE_RUN.finditer(text))


def enclosed_spans(sentence: str) -> tuple[tuple[int, int], ...]:
    """The offsets each code span or matched pair of brackets covers.

    Only a matched pair encloses anything, so a stray bracket such as the one in "1)" never swallows the sentence.
    """
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


def protected_spans(text: str) -> tuple[tuple[int, int], ...]:
    """The offsets of what a rule reading prose steps over, such as code, a URL, a link target, or a quotation."""
    return tuple((match.start(), match.end()) for match in _PROTECTED.finditer(text))


def is_protected(offset: int, spans: tuple[tuple[int, int], ...]) -> bool:
    """Whether an offset falls inside any of the spans."""
    return any(start <= offset < end for start, end in spans)


def is_wide(character: str) -> bool:
    """Whether a character is set full width, as Chinese, Japanese, and Korean text and its punctuation are."""
    return bool(character) and unicodedata.east_asian_width(character) in {'W', 'F'}
