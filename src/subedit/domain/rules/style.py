import dataclasses
import re
import typing

from ..models.diagnostic import Diagnostic, Fix, FixKind, RuleMetadata, Severity
from ..models.prose import is_protected, is_wide, protected_spans, words_pattern
from ..models.prose_unit import ProseLine, ProseUnit
from ..models.rule_option import ChoiceOption, CountOption, ReplacementsOption
from ..models.title_case import title_case
from ..ports.rule import Rule, RuleContext
from .markdown import title_case_settings


_COLON = re.compile(r'[:：]')
# A label is a few words with no sentence punctuation,
# though a comma may join two halves, set before the colon that opens a list item or paragraph.
_LABEL = re.compile(
    r'^(?P<open>\*\*|__)?'
    r'(?P<label>(?:`[^`]*`|[^\s*_:：.,;!?。，；！？`])(?:`[^`]*`|\.(?=\S)|[^*_:：.;!?。；！？`]){0,79}?)'
    r'(?P<close>\*\*|__)?(?P<note>\s*\([^()]*\))?(?P<colon>[:：])'
)
_MAX_LABEL_WORDS = CountOption('max-label-words', 5)
_MAX_BOLD_LABEL_WORDS = CountOption('max-bold-label-words', 10)
_MAX_FULL_WIDTH_LABEL_CHARACTERS = CountOption('max-full-width-label-characters', 12)
# A paragraph, unlike a list item, opens with a label only as a capitalized tag such as Note.
_MAX_TAG_WORDS = CountOption('max-tag-words', 3)
# The auxiliary and modal verbs, each finite in every form listed,
# which make the words before a colon a clause, as in "The write is idempotent:", rather than a label.
_AUXILIARIES = frozenset(
    {
        'am',
        'are',
        'can',
        'could',
        'did',
        'do',
        'does',
        'had',
        'has',
        'have',
        'is',
        'may',
        'might',
        'must',
        'shall',
        'should',
        'was',
        'were',
        'will',
        'would',
    }
)
_PARENTHESES = re.compile(r'[(（](?P<inside>[^()（）]*)[)）]')
# No space goes between a parenthesis and the punctuation or bracket beside it.
_HUGS_A_PARENTHESIS = frozenset('.,;:!?，。、；：！？「」『』"\'[]{}<>/')
# Half-width parentheses, spaced from the words outside, are the house style, and full-width ones the CJK standard.
_HALF_WIDTH, _FULL_WIDTH = 'half-width', 'full-width'
_PARENTHESIS_STYLE = ChoiceOption('style', _HALF_WIDTH, choices=(_HALF_WIDTH, _FULL_WIDTH))
# Words the project writes otherwise, each set to the one it prefers.
_REPLACEMENTS = ReplacementsOption('replacements', {'包括': '包含'})
# 而不是 already sets B before what it is not, and 是不是 asks a question.
# After the comma, a 是 opening a word such as 是否 or 是因為 asks whether or gives a reason, and names no B.
_CONTRAST = re.compile(r'(?<![而是])不是[^，,。；;！!？?]{1,40}[，,]\s*(?:而)?是(?!否|因為|因为|由於|由于|為了|为了)')


_CLAUSE_MESSAGE = (
    'A colon joins clauses or leads into an inline list here. '
    'A colon belongs in a heading, after a label, or at the end of a line that a list or block follows. '
    'Split the sentence in two, or turn the inline list into a list.'
)
_LABEL_MESSAGE = (
    'The words before this colon may open a sentence rather than name the item, '
    'since they run long or carry a verb such as is or can. '
    'If they name the item, shorten them to a label. If they open a sentence, split it in two.'
)


class MidSentenceColonRule(Rule[ProseUnit]):
    metadata = RuleMetadata(
        rule_id='mid-sentence-colon',
        summary='A colon stands only in a heading, after a label, or at the end of a line leading into a list or block.',
        fix_kind=FixKind.REWRITE,
        options=(_MAX_LABEL_WORDS, _MAX_BOLD_LABEL_WORDS, _MAX_FULL_WIDTH_LABEL_CHARACTERS, _MAX_TAG_WORDS),
    )
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if unit.is_heading or not unit.is_own_prose:
            return
        limits = _LabelLimits.of(context)
        for line in unit.prose_lines():
            spans = protected_spans(line.text)
            label = _label_colon(line, limits)
            sure_label = label.colon if label is not None and label.is_sure else None
            unsure_label = label.colon if label is not None and not label.is_sure else None
            trailing = line.text.rstrip().rstrip('*_')
            for colon in _COLON.finditer(line.text):
                offset = colon.start()
                if offset == sure_label or is_protected(offset, spans) or not _closes_a_clause(line.text, offset):
                    continue
                if offset >= len(trailing) - 1 and line.ends_paragraph:
                    continue
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(offset, offset + 1),
                    message=_LABEL_MESSAGE if offset == unsure_label else _CLAUSE_MESSAGE,
                    fix=Fix.rewrite(),
                    # Whether the words before a colon name the item or open a sentence is a guess.
                    tentative=offset == unsure_label,
                )


class ParenthesisStyleRule(Rule[ProseUnit]):
    metadata = RuleMetadata(
        rule_id='parenthesis-style',
        summary='Parentheses around prose take the width the project picks, spaced as that width is.',
        fix_kind=FixKind.TARGETED,
        options=(_PARENTHESIS_STYLE,),
    )
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not unit.is_own_prose:
            return
        full_width_style = context.settings(self.metadata.rule_id).value(_PARENTHESIS_STYLE) == _FULL_WIDTH
        for line in unit.prose_lines():
            spans = protected_spans(line.text)
            for parentheses in _PARENTHESES.finditer(line.text):
                start, end = parentheses.span()
                if is_protected(start, spans) or line.text[start - 1 : start] == ']':
                    continue
                inside = parentheses.group('inside')
                full_width = parentheses.group().startswith('（') or parentheses.group().endswith('）')
                # A call such as foo(bar) holds no space and no CJK text, so it is code, not an aside.
                if not full_width and not (any(map(is_wide, inside)) or ' ' in inside):
                    continue
                if full_width_style and _beside_cjk(line.text, start, end):
                    start, end = _spaces_around(line.text, start, end)
                    width, styled = _FULL_WIDTH, f'（{inside.strip()}）'
                else:
                    width, styled = _HALF_WIDTH, _half_width(line.text, start, end, inside)
                if styled == line.text[start:end]:
                    continue
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(start, end),
                    message=(f'Parentheses here are {width} in this project, so this reads as "{styled.strip()}".'),
                    fix=Fix.targeted(line.edit(start, end, styled)),
                )


class DiscouragedWordRule(Rule[ProseUnit]):
    metadata = RuleMetadata(
        rule_id='discouraged-word',
        summary='Prose uses the word the project prefers in place of one it discourages.',
        fix_kind=FixKind.TARGETED,
        options=(_REPLACEMENTS,),
    )
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not unit.is_own_prose:
            return
        replacements = context.settings(self.metadata.rule_id).value(_REPLACEMENTS)
        if not replacements:
            return
        discouraged = words_pattern(replacements)
        for line in unit.prose_lines():
            spans = protected_spans(line.text)
            for found in discouraged.finditer(line.text):
                if is_protected(found.start(), spans):
                    continue
                replacement = replacements[found.group()]
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(*found.span()),
                    message=f'This project writes "{replacement}" in place of "{found.group()}".',
                    fix=Fix.targeted(line.edit(*found.span(), replacement)),
                )


class ContrastFramingRule(Rule[ProseUnit]):
    metadata = RuleMetadata(
        rule_id='contrast-framing',
        summary='A Chinese sentence states what something is, rather than framing it against what it is not.',
        fix_kind=FixKind.REWRITE,
        default_severity=Severity.WARNING,
    )
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not unit.is_own_prose:
            return
        for line in unit.prose_lines():
            for found in _CONTRAST.finditer(line.text):
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(*found.span()),
                    message=(
                        'This sentence frames what something is against what it is not, as in 不是 A，是 B. '
                        'State B directly, or write 是 B 而非 A where the contrast matters.'
                    ),
                    fix=Fix.rewrite(),
                )


class ListLabelTitleCaseRule(Rule[ProseUnit]):
    metadata = RuleMetadata(
        rule_id='list-label-title-case',
        summary='The English words of a list item label are in Title Case.',
        fix_kind=FixKind.TARGETED,
    )
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        # Title Case and its exceptions are set once, on the heading rule, and labels follow them.
        exceptions, style = title_case_settings(context)
        for line, label in _list_labels(unit, context):
            words = label.group('label')
            cased = title_case(words, exceptions, style)
            if cased == words:
                continue
            yield Diagnostic(
                rule_id=self.metadata.rule_id,
                range=line.span(*label.span('label')),
                message=f'A list item label is in Title Case, so it reads "{cased}".',
                fix=Fix.targeted(line.edit(*label.span('label'), cased)),
            )


class ListLabelNotBoldRule(Rule[ProseUnit]):
    metadata = RuleMetadata(
        rule_id='list-label-not-bold',
        summary='A list item label is bold wherever the text renders, so it reads as the title of its item.',
        fix_kind=FixKind.TARGETED,
    )
    surface = ProseUnit

    def check(self, unit: ProseUnit, context: RuleContext) -> typing.Iterable[Diagnostic]:
        if not unit.renders_markup:
            return
        for line, label in _list_labels(unit, context):
            start, end = label.span('label')
            opener = label.group('open')
            if not opener:
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(start, end),
                    message=f'A list item label is bold where the text renders, so it reads "**{label.group("label")}**".',
                    fix=Fix.targeted(line.edit(start, start, '**'), line.edit(end, end, '**')),
                )
            # A bold label may close its bold after the colon, which belongs outside the bold.
            elif not label.group('close') and line.text.startswith(opener, label.end()):
                yield Diagnostic(
                    rule_id=self.metadata.rule_id,
                    range=line.span(start, label.end() + len(opener)),
                    message=f'A bold list item label closes its bold before the colon, as in "**{label.group("label")}**:".',
                    fix=Fix.targeted(
                        line.edit(end, end, opener), line.edit(label.end(), label.end() + len(opener), '')
                    ),
                )


def _list_labels(unit: ProseUnit, context: RuleContext) -> typing.Iterator[tuple[ProseLine, re.Match[str]]]:
    limits = _LabelLimits.of(context)
    for line in unit.prose_lines():
        if not line.opens_item:
            continue
        label = _LABEL.match(line.text)
        if label is not None and _is_label(label.group('label'), limits):
            yield line, label


def _half_width(text: str, start: int, end: int, inside: str) -> str:
    before = text[start - 1] if start else ''
    after = text[end] if end < len(text) else ''
    return (
        (' ' if before and not before.isspace() and before not in _HUGS_A_PARENTHESIS else '')
        + f'({inside.strip()})'
        + (' ' if after and not after.isspace() and after not in _HUGS_A_PARENTHESIS else '')
    )


# An aside in or beside CJK text takes full-width parentheses, while one in English keeps half-width ones.
def _beside_cjk(text: str, start: int, end: int) -> bool:
    before = text[:start].rstrip()[-1:]
    after = text[end:].lstrip()[:1]
    return any(map(is_wide, text[start + 1 : end - 1])) or is_wide(before) or is_wide(after)


# Full-width parentheses carry their own spacing, so the spaces beside them go,
# though not a line's indent, nor the trailing spaces that mark a Markdown hard break.
def _spaces_around(text: str, start: int, end: int) -> tuple[int, int]:
    while start > 0 and text[start - 1] == ' ' and text[: start - 1].strip():
        start -= 1
    if text[end:].strip():
        while text[end] == ' ':
            end += 1
    return start, end


@dataclasses.dataclass(frozen=True, slots=True)
class _LabelLimits:
    words: int
    bold_words: int
    full_width_characters: int
    tag_words: int

    @classmethod
    def of(cls, context: RuleContext) -> '_LabelLimits':
        """The colon rule owns what a label is, and the list label rules follow it, so they never disagree."""
        settings = context.settings(MidSentenceColonRule.metadata.rule_id)
        return cls(
            words=settings.value(_MAX_LABEL_WORDS),
            bold_words=settings.value(_MAX_BOLD_LABEL_WORDS),
            full_width_characters=settings.value(_MAX_FULL_WIDTH_LABEL_CHARACTERS),
            tag_words=settings.value(_MAX_TAG_WORDS),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class _LabelColon:
    colon: int
    # Whether the words before the colon surely form a label, rather than possibly a clause.
    is_sure: bool


# A list item may open with any short label, while a paragraph opens with one only as a capitalized tag such as Note.
# A label the author set in bold is taken at their word, up to a longer limit.
# Past a limit, words in a label's place may still be one, while a paragraph that opens with no tag opens a sentence.
def _label_colon(line: ProseLine, limits: _LabelLimits) -> _LabelColon | None:
    label = _LABEL.match(line.text) if line.opens_item or line.opens_paragraph else None
    if label is None:
        return None
    text, colon = label.group('label'), label.start('colon')
    if label.group('open'):
        return _LabelColon(colon, is_sure=len(text.split()) <= limits.bold_words)
    if line.opens_item:
        return _LabelColon(colon, is_sure=_is_label(text, limits))
    return _LabelColon(colon, is_sure=True) if _is_label(text, limits) and _is_tag(text, limits) else None


def _is_label(text: str, limits: _LabelLimits) -> bool:
    if any(map(is_wide, text)):
        return len(text.strip()) <= limits.full_width_characters
    words = text.split()
    if any(word.lower() in _AUXILIARIES for word in words):
        return False
    return 0 < len(words) <= limits.words and not text.rstrip().endswith(('http', 'https'))


def _is_tag(text: str, limits: _LabelLimits) -> bool:
    words = text.split()
    return 0 < len(words) <= limits.tag_words and all(word[:1].isupper() for word in words)


# A half-width colon closes a clause only before a space or the end of the line, which leaves out a time or a scheme.
def _closes_a_clause(text: str, offset: int) -> bool:
    if text[offset] == '：':
        return True
    following = text[offset + 1 : offset + 4]
    if following.startswith(('**', '__')):
        following = following[2:]
    return not following or following[0].isspace()
